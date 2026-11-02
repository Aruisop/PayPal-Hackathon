"""Connected HTTP journey with temporary storage and fake payment/model adapters."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select, update

from app import create_app
from app.__main__ import main
from app.planning.catalog import availability
from app.planning.demo_catalog import prepare_demo_catalog
from app.shared.storage import catalog_offers, catalog_resources, metadata
from test_recommendations import FixtureEncoder
from test_workshop_slice import FakePayPal


class GuidedJourneyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'GEMINI_API_KEY': ''}); self.env.start()
        self.fake = FakePayPal()
        self.app = create_app(dict(DATABASE_URL='sqlite:///' + (Path(self.directory.name) / 'journey.db').as_posix(),
            APP_ENV='development', APP_ORIGIN='http://localhost', COOKIE_SECURE=False, TESTING=True),
            paypal=self.fake, encoder=FixtureEncoder())
        self.store = self.app.extensions['store']
        self.owner, self.member, self.outsider = [self.app.test_client() for _ in range(3)]
        self.configs = {client: client.get('/api/config').json for client in (self.owner, self.member, self.outsider)}
        group = self.post(self.owner, '/api/groups', {'name': 'A common ground plan'}).json
        self.base = f'/api/groups/{group["id"]}'
        self.invite = group['inviteURL'].split('invite=')[1]

    def tearDown(self):
        self.store.engine.dispose(); self.directory.cleanup(); self.env.stop()

    def post(self, client, path, body):
        return client.post(path, json=body, headers={'Origin': 'http://localhost',
            'X-CSRF-Token': self.configs[client]['csrfToken']})

    def room(self, client=None):
        response = (client or self.owner).get(self.base + '/room')
        self.assertEqual(response.status_code, 200)
        return response.json

    def confirm(self, client, likes):
        response = self.post(client, self.base + '/preferences', {'rawText': 'Any day and time under $20', 'userTz': 'UTC'})
        self.assertEqual(response.status_code, 200)
        response = self.post(client, self.base + '/preferences/confirm', {'confirmedConstraints': {
            'budget_cents': 2000, 'soft_preferences': likes, 'timezone': 'UTC'}})
        self.assertEqual(response.status_code, 200)

    def snapshot(self):
        with self.store.engine.connect() as connection:
            return {table.name: [dict(row) for row in connection.execute(select(table)).mappings()]
                    for table in metadata.sorted_tables}

    def test_saved_journey_from_invite_to_comparison_to_individual_payments_and_tickets(self):
        self.assertEqual(self.room()['journey']['action'], 'invite')
        self.post(self.member, '/api/groups/join', {'inviteToken': self.invite})
        self.assertEqual(self.room()['journey']['action'], 'preferences')
        self.confirm(self.owner, ['space adventure'])
        self.assertEqual(self.room()['journey']['action'], 'compare')
        self.assertIn('1 of 2', self.room()['journey']['detail'])
        self.assertEqual(self.room(self.member)['journey']['action'], 'preferences')
        self.confirm(self.member, ['emotional stories'])
        self.assertEqual(self.room()['journey']['stage'], 'compare')
        recommended = self.post(self.owner, self.base + '/recommendations', {'domain': 'movie'}).json
        self.assertEqual(recommended['recommendation']['mode'], 'semantic')
        self.assertEqual(len(recommended['matches']), 3)
        offer = recommended['matches'][0]
        selection = dict(offerID=offer['id'], resourceIDs=offer['proposedResourceIDs'])
        quote = self.post(self.owner, self.base + '/quote', selection)
        self.assertEqual(quote.status_code, 200)
        self.assertEqual(sum(share['shareCents'] for share in quote.json['shares']), quote.json['totalCents'])
        self.assertEqual(self.post(self.owner, self.base + '/freeze', selection).status_code, 200)
        self.assertEqual(self.room()['journey']['stage'], 'payment')
        for client in (self.owner, self.member):
            self.assertNotEqual(client.get(self.base + '/ticket').status_code, 200)
            self.assertEqual(self.post(client, self.base + '/booking/consent', {}).status_code, 200)
            order = self.post(client, self.base + '/contributions/order', {})
            self.assertEqual(order.status_code, 200)
            self.fake.approve(order.json['orderID'])
            self.assertEqual(self.post(client, self.base + '/contributions/authorize', {}).status_code, 200)
        self.assertNotEqual(self.owner.get(self.base + '/ticket').status_code, 200)
        result = self.post(self.owner, self.base + '/finalize', {})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['state'], 'CONFIRMED')
        self.assertEqual(self.room()['journey']['stage'], 'ticket')
        owner_ticket = self.owner.get(self.base + '/ticket').json
        member_ticket = self.member.get(self.base + '/ticket').json
        self.assertNotEqual(owner_ticket['ticketCode'], member_ticket['ticketCode'])
        self.assertEqual(self.outsider.get(self.base + '/ticket').status_code, 404)

    def test_planning_version_changes_without_disclosing_a_peers_values_or_mutating_tables(self):
        self.post(self.member, '/api/groups/join', {'inviteToken': self.invite})
        first = self.room()
        self.confirm(self.member, ['a private unusual taste'])
        before = self.snapshot()
        second = self.room()
        self.assertNotEqual(first['planningVersion'], second['planningVersion'])
        self.assertNotIn('a private unusual taste', json.dumps(second))
        self.assertNotIn('budget_cents', json.dumps(second))
        self.assertFalse(second['journey']['ownConfirmed'])
        self.assertEqual(self.snapshot(), before)

    def test_catalog_reports_past_and_adjacent_capacity_without_changing_saved_resources(self):
        with self.store.engine.begin() as connection:
            connection.execute(update(catalog_resources).where(catalog_resources.c.offer_id == 'movie-cosmic-odyssey-fri',
                catalog_resources.c.col_number % 2 == 0).values(state='HELD'))
            connection.execute(update(catalog_offers).where(catalog_offers.c.id == 'movie-neon-shadows-sat').values(
                schedule_time='2000-01-01T00:00:00+00:00'))
        before = self.snapshot()
        result = self.owner.get('/api/catalog/offers')
        self.assertEqual(result.status_code, 200)
        offers = {offer['id']: offer for offer in result.json['offers']}
        self.assertEqual(offers['movie-cosmic-odyssey-fri']['availability'], {'status': 'unavailable', 'groupSizes': []})
        self.assertEqual(offers['movie-neon-shadows-sat']['availability']['status'], 'past')
        self.assertEqual(offers['movie-silent-echoes-sun']['availability']['groupSizes'], [2, 3, 4])
        self.assertFalse(result.json['summary']['inventoryReserved'])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.owner.get('/api/catalog/offers?domain=invalid').status_code, 400)

    def test_prepare_demo_appends_future_sessions_idempotently_and_preserves_all_original_records(self):
        before = self.snapshot()
        result = prepare_demo_catalog(self.store, date(2035, 1, 1))
        self.assertEqual(result['createdCount'], 5)
        self.assertFalse(result['existingRecordsChanged'])
        after = self.snapshot()
        for name, rows in before.items():
            self.assertEqual([row for row in after[name] if row in rows], rows)
            if name not in ('catalog_offers', 'catalog_resources'):
                self.assertEqual(after[name], rows)
        self.assertEqual(prepare_demo_catalog(self.store, date(2035, 1, 1))['createdCount'], 0)
        self.assertEqual(self.snapshot(), after)
        result = availability(self.store.offers(), datetime(2035, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(result['summary']['upcomingCount'], 5)
        self.assertEqual(result['summary']['pastCount'], 5)
        self.assertTrue(all(offer['availability']['groupSizes'] == [2, 3, 4] for offer in result['offers']
                            if offer['availability']['status'] != 'past'))

    def test_repeated_demo_preparation_never_releases_a_new_sessions_held_inventory(self):
        prepare_demo_catalog(self.store, date(2035, 1, 1))
        with self.store.engine.begin() as connection:
            connection.execute(update(catalog_resources).where(catalog_resources.c.offer_id.like('demo-%')).values(state='HELD'))
        before = self.snapshot()
        self.assertEqual(prepare_demo_catalog(self.store, date(2035, 1, 1))['createdCount'], 0)
        self.assertEqual(self.snapshot(), before)

    def test_production_rejects_demo_command_before_any_store_is_opened(self):
        with patch.dict(os.environ, {'APP_ENV': 'production'}), patch('app.__main__.load_env'), \
             patch('app.__main__.Store') as store, patch('sys.argv', ['app', 'prepare-demo']), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 2)
        store.assert_not_called()
