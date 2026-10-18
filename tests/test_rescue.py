"""Counterfactual plans never change consent, another member or booked inventory."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select, update

from ai_planner import AIError, DeterministicCatalogMatcher
from rescue import PlanRescue
from server import create_app
from storage import catalog_offers, catalog_resources, group_member_preferences, purchase_contributions, shared_purchases
from test_workshop_slice import FakePayPal


class RescueTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'GEMINI_API_KEY': ''}); self.env.start()
        self.fake = FakePayPal()
        self.app = create_app(dict(DATABASE_URL='sqlite:///' + (Path(self.directory.name) / 'rescue.db').as_posix(),
            APP_ENV='development', APP_ORIGIN='http://localhost', COOKIE_SECURE=False, TESTING=True), paypal=self.fake)
        self.store = self.app.extensions['store']
        self.groups = self.app.extensions['groups']
        self.planning = self.app.extensions['booking'].planning
        self.owner, _ = self.store.new_participant(); self.member, _ = self.store.new_participant()
        self.outsider, _ = self.store.new_participant()
        group = self.groups.create(self.owner['id'], 'Plan together'); self.gid = group['id']
        self.groups.join(self.member['id'], group['inviteURL'].split('invite=')[1])
        self.rescue = PlanRescue(self.store)

    def tearDown(self):
        self.store.engine.dispose(); self.directory.cleanup(); self.env.stop()

    def confirm(self, participant, constraints):
        self.planning.submit_preference(participant['id'], self.gid, 'Any day and time, flexible budget', 'UTC')
        self.planning.confirm_preference(participant['id'], self.gid, constraints)

    def snapshot(self):
        with self.store.engine.connect() as connection:
            return {table.name: [dict(row) for row in connection.execute(select(table)).mappings()]
                    for table in (group_member_preferences, catalog_resources, shared_purchases, purchase_contributions)}

    def test_budget_rescue_is_exact_verified_and_read_only(self):
        self.confirm(self.owner, {'budget_cents': 100})
        self.confirm(self.member, {'budget_cents': 9999})
        before = self.snapshot()
        with patch('urllib.request.urlopen') as network:
            result = self.rescue.suggest(self.owner['id'], self.gid)
        network.assert_not_called()
        self.assertEqual(result['engine'], 'verified_rules')
        self.assertFalse(result['saved'])
        self.assertTrue(result['requiresConfirmation'])
        self.assertEqual(result['baselineMatchCount'], 0)
        self.assertEqual(result['proposals'][0]['ownShareCents'], 1200)
        for proposal in result['proposals']:
            self.assertEqual(proposal['constraints']['budget_cents'], proposal['ownShareCents'])
            self.assertEqual(proposal['changes'][0]['before'], 100)
            with self.store.engine.connect() as connection:
                offers = self.planning._offers(connection, 'movie')
            offer = next(offer for offer in offers if offer['id'] == proposal['id'])
            self.assertTrue(DeterministicCatalogMatcher().match([proposal['constraints'], {'budget_cents': 9999}], [offer], 2)['matches'])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.fake.create_calls, 0)
        self.assertNotIn('9999', json.dumps(result))

    def test_other_members_budget_is_not_relaxed_or_disclosed(self):
        self.confirm(self.owner, {'budget_cents': 10000})
        self.confirm(self.member, {'budget_cents': 73})
        result = self.rescue.suggest(self.owner['id'], self.gid)
        self.assertEqual(result['status'], 'blocked_elsewhere')
        self.assertEqual(result['proposals'], [])
        self.assertNotIn('73', json.dumps(result))
        own = self.rescue.suggest(self.member['id'], self.gid)
        self.assertTrue(own['proposals'])
        self.assertTrue(all(p['changes'][0]['before'] == 73 for p in own['proposals']))

    def test_time_edits_are_specific_and_others_stay_fixed(self):
        self.confirm(self.owner, {'budget_cents': 10000, 'preferred_days': ['monday'], 'dates': ['2035-01-01'],
            'time_window': {'earliest': '23:00'}, 'timezone': 'Asia/Kolkata'})
        self.confirm(self.member, {'budget_cents': 10000})
        result = self.rescue.suggest(self.owner['id'], self.gid)
        self.assertTrue(result['proposals'])
        for proposal in result['proposals']:
            fields = {c['field'] for c in proposal['changes']}
            self.assertIn('dates', fields)
            self.assertIn('preferred_days', fields)
            self.assertIn('2035-01-01', proposal['constraints']['dates'])
            self.assertIn('monday', proposal['constraints']['preferred_days'])
            self.assertEqual(proposal['constraints']['timezone'], 'Asia/Kolkata')

    def test_excursion_remainder_uses_actual_roster_order(self):
        third, _ = self.store.new_participant()
        group = self.groups.view(self.owner['id'], self.gid)
        self.groups.join(third['id'], group['inviteURL'].split('invite=')[1])
        for participant in (self.owner, self.member, third): self.confirm(participant, {'budget_cents': 1})
        # Other members can afford the excursion; only the current member is changed.
        self.planning.confirm_preference(self.member['id'], self.gid, {'budget_cents': 10000})
        self.planning.confirm_preference(third['id'], self.gid, {'budget_cents': 10000})
        result = self.rescue.suggest(self.owner['id'], self.gid, 'excursion')
        hundred = next(p for p in result['proposals'] if p['totalCents'] == 10000)
        self.assertEqual(hundred['ownShareCents'], 3334)
        self.assertEqual(hundred['budgetIncreaseCents'], 3333)

    def test_membership_confirmation_and_frozen_boundaries(self):
        with self.assertRaises(AIError) as error:
            self.rescue.suggest(self.outsider['id'], self.gid)
        self.assertEqual(error.exception.status, 404)
        self.assertEqual(self.rescue.suggest(self.owner['id'], self.gid)['status'], 'needs_confirmation')
        for participant in (self.owner, self.member): self.confirm(participant, {'budget_cents': 10000})
        self.app.extensions['booking'].freeze(self.owner['id'], self.gid, 'movie-cosmic-odyssey-fri',
            ['res-movie-cosmic-odyssey-fri-A1', 'res-movie-cosmic-odyssey-fri-A2'])
        with self.assertRaises(AIError) as error:
            self.rescue.suggest(self.owner['id'], self.gid)
        self.assertEqual(error.exception.issue, 'ROSTER_ALREADY_FROZEN')

    def test_unavailable_resources_and_past_offers_never_become_suggestions(self):
        for participant in (self.owner, self.member): self.confirm(participant, {'budget_cents': 10000})
        with self.store.engine.begin() as connection:
            connection.execute(update(catalog_resources).where(catalog_resources.c.offer_id == 'movie-cosmic-odyssey-fri').values(state='BOOKED'))
            changed = connection.execute(update(catalog_offers).where(catalog_offers.c.id == 'movie-silent-echoes-sun').values(schedule_time='2000-01-01T10:00:00+00:00'))
            self.assertEqual(changed.rowcount, 1)
        result = self.rescue.suggest(self.owner['id'], self.gid)
        self.assertNotIn('movie-cosmic-odyssey-fri', [p['id'] for p in result['proposals']])
        self.assertNotIn('movie-silent-echoes-sun', [p['id'] for p in result['proposals']])
        for proposal in result['proposals']: self.assertTrue(proposal['fitsNow'])

    def test_http_ignores_spoofed_identity_and_requires_csrf(self):
        client = self.app.test_client(); config = client.get('/api/config').json
        group = self.groups.create(config['participantID'], 'Solo')
        endpoint = f'/api/groups/{group["id"]}/rescue'
        self.assertEqual(client.post(endpoint, json={}).status_code, 403)
        headers = {'Origin': 'http://localhost', 'X-CSRF-Token': config['csrfToken']}
        response = client.post(endpoint, json={'domain': 'movie', 'participantID': self.owner['id'], 'groupID': self.gid}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['status'], 'needs_members')
        self.assertEqual(client.post(f'/api/groups/{self.gid}/rescue', json={}, headers=headers).status_code, 404)
        self.assertEqual(client.post(endpoint, json={'domain': 'invented'}, headers=headers).status_code, 400)
