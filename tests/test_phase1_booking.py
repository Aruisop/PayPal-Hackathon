"""Tests for Phase 1: Collaborative movie catalog, roster freeze, and exact integer cent allocation."""
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import insert, inspect, select

from collab_booking import split_equal_cents
from server import create_app
from storage import (Store, attempts, bookings, catalog_offers, catalog_resources,
                     entitlements, group_member_profiles, group_memberships,
                     participants, purchase_contributions, shared_purchases,
                     versions, workshop_groups, workshops)
from test_workshop_slice import FakePayPal


class Phase1BookingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.fake = FakePayPal()
        self.config = dict(
            DATABASE_URL='sqlite:///' + (Path(self.directory.name) / 'phase1.db').as_posix(),
            APP_ORIGIN='http://localhost',
            COOKIE_SECURE=False,
            APP_ENV='development',
            TESTING=True
        )
        self.app = create_app(self.config, paypal=self.fake)
        self.organizer = self.app.test_client()
        self.member = self.app.test_client()
        self.outsider = self.app.test_client()
        self.csrf = {client: client.get('/api/config').json['csrfToken']
                     for client in (self.organizer, self.member, self.outsider)}

    def tearDown(self):
        self.app.extensions['store'].engine.dispose()
        self.directory.cleanup()

    def post(self, client, path, body):
        return client.post(path, json=body, headers={
            'Origin': 'http://localhost',
            'X-CSRF-Token': self.csrf[client]
        })

    def create_group_with_member(self):
        created = self.post(self.organizer, '/api/groups', {'name': 'Movie Night'}).json
        invite_token = created['inviteURL'].split('invite=', 1)[1]
        self.post(self.member, '/api/groups/join', {'inviteToken': invite_token})
        return created['id']

    def test_catalog_seeds_three_movies_and_two_excursions(self):
        resp = self.organizer.get('/api/catalog/offers')
        self.assertEqual(resp.status_code, 200)
        offers = resp.json['offers']
        self.assertGreaterEqual(len(offers), 5)
        movies = [o for o in offers if o['domain'] == 'movie']
        excursions = [o for o in offers if o['domain'] == 'excursion']
        self.assertGreaterEqual(len(movies), 3)
        self.assertGreaterEqual(len(excursions), 2)

        # Check adjacent seats seeded
        for movie in movies:
            self.assertEqual(len(movie['resources']), 8)
            self.assertTrue(all(r['state'] == 'FREE' for r in movie['resources']))

    def test_split_equal_cents_rounding_and_sum_guarantee(self):
        # PRD example: $100.00 among three participants gives $33.34, $33.33 and $33.33
        p = ['user_1', 'user_2', 'user_3']
        shares = split_equal_cents(10000, p)
        self.assertEqual(shares['user_1'], 3334)
        self.assertEqual(shares['user_2'], 3333)
        self.assertEqual(shares['user_3'], 3333)
        self.assertEqual(sum(shares.values()), 10000)

        # $25.00 among 3 participants -> 834, 833, 833
        shares_25 = split_equal_cents(2500, p)
        self.assertEqual(shares_25['user_1'], 834)
        self.assertEqual(shares_25['user_2'], 833)
        self.assertEqual(shares_25['user_3'], 833)
        self.assertEqual(sum(shares_25.values()), 2500)

        # Exact clean split: $48.00 among 3 participants -> 1600 each
        shares_48 = split_equal_cents(4800, p)
        self.assertEqual(list(shares_48.values()), [1600, 1600, 1600])
        self.assertEqual(sum(shares_48.values()), 4800)

        # Invariant: repeat requests return identical allocation in stable order
        shares_repeat = split_equal_cents(10000, p)
        self.assertEqual(shares, shares_repeat)

    def test_client_tampering_of_price_or_share_is_ignored(self):
        group_id = self.create_group_with_member()
        offers = self.organizer.get('/api/catalog/offers?domain=movie').json['offers']
        target_offer = offers[0]
        seat_ids = [target_offer['resources'][0]['id'], target_offer['resources'][1]['id']]

        # Client attempts tampering price to $0.01
        quote_resp = self.post(self.organizer, f'/api/groups/{group_id}/quote', {
            'offerID': target_offer['id'],
            'resourceIDs': seat_ids,
            'amount': '0.01',
            'totalCents': 1
        })
        self.assertEqual(quote_resp.status_code, 200)
        # Server must enforce authoritative catalog price: 1600 cents * 2 members = 3200 cents
        expected_total = target_offer['priceMinor'] * 2
        self.assertEqual(quote_resp.json['totalCents'], expected_total)
        self.assertEqual(quote_resp.json['totalValue'], '32.00')

    def test_only_organizer_can_freeze_roster(self):
        group_id = self.create_group_with_member()
        offers = self.organizer.get('/api/catalog/offers?domain=movie').json['offers']
        target_offer = offers[0]
        seat_ids = [target_offer['resources'][0]['id'], target_offer['resources'][1]['id']]

        # Member tries to freeze -> 403
        member_attempt = self.post(self.member, f'/api/groups/{group_id}/freeze', {
            'offerID': target_offer['id'],
            'resourceIDs': seat_ids
        })
        self.assertEqual(member_attempt.status_code, 403)
        self.assertEqual(member_attempt.json['error'], 'ORGANIZER_REQUIRED')

        # Organizer freezes -> 200
        org_freeze = self.post(self.organizer, f'/api/groups/{group_id}/freeze', {
            'offerID': target_offer['id'],
            'resourceIDs': seat_ids
        })
        self.assertEqual(org_freeze.status_code, 200)
        self.assertTrue(org_freeze.json['hasBooking'])
        self.assertEqual(org_freeze.json['state'], 'AWAITING_AUTHORIZATIONS')

    def test_duplicate_freeze_rejected(self):
        group_id = self.create_group_with_member()
        offers = self.organizer.get('/api/catalog/offers?domain=movie').json['offers']
        target_offer = offers[0]
        seat_ids = [target_offer['resources'][0]['id'], target_offer['resources'][1]['id']]

        self.post(self.organizer, f'/api/groups/{group_id}/freeze', {
            'offerID': target_offer['id'],
            'resourceIDs': seat_ids
        })

        # Second freeze attempt -> 409 ROSTER_ALREADY_FROZEN
        second_freeze = self.post(self.organizer, f'/api/groups/{group_id}/freeze', {
            'offerID': target_offer['id'],
            'resourceIDs': seat_ids
        })
        self.assertEqual(second_freeze.status_code, 409)
        self.assertEqual(second_freeze.json['error'], 'ROSTER_ALREADY_FROZEN')

    def test_late_join_after_freeze_rejected(self):
        group_id = self.create_group_with_member()
        group_data = self.organizer.get(f'/api/groups/{group_id}').json
        invite_token = group_data['inviteURL'].split('invite=', 1)[1]

        offers = self.organizer.get('/api/catalog/offers?domain=movie').json['offers']
        target_offer = offers[0]
        seat_ids = [target_offer['resources'][0]['id'], target_offer['resources'][1]['id']]

        self.post(self.organizer, f'/api/groups/{group_id}/freeze', {
            'offerID': target_offer['id'],
            'resourceIDs': seat_ids
        })

        # Late joiner tries to join after freeze -> 409 ROSTER_FROZEN
        late_join = self.post(self.outsider, '/api/groups/join', {'inviteToken': invite_token})
        self.assertEqual(late_join.status_code, 409)
        self.assertEqual(late_join.json['error'], 'ROSTER_FROZEN')

    def test_two_groups_cannot_reserve_same_seats(self):
        group_1 = self.create_group_with_member()

        # Create second group
        g2_created = self.post(self.outsider, '/api/groups', {'name': 'Rival Group'}).json
        g2_token = g2_created['inviteURL'].split('invite=', 1)[1]
        # Have organizer join g2 as a member for group of 2
        self.post(self.organizer, '/api/groups/join', {'inviteToken': g2_token})
        group_2 = g2_created['id']

        offers = self.organizer.get('/api/catalog/offers?domain=movie').json['offers']
        target_offer = offers[0]
        seat_ids = [target_offer['resources'][0]['id'], target_offer['resources'][1]['id']]

        # Group 1 freezes seats
        self.post(self.organizer, f'/api/groups/{group_1}/freeze', {
            'offerID': target_offer['id'],
            'resourceIDs': seat_ids
        })

        # Group 2 tries to freeze the SAME seats -> 409 SEAT_UNAVAILABLE
        g2_freeze = self.post(self.outsider, f'/api/groups/{group_2}/freeze', {
            'offerID': target_offer['id'],
            'resourceIDs': seat_ids
        })
        self.assertEqual(g2_freeze.status_code, 409)
        self.assertEqual(g2_freeze.json['error'], 'SEAT_UNAVAILABLE')

    def test_cross_member_private_data_isolation(self):
        group_id = self.create_group_with_member()

        # Set custom aliases
        self.post(self.organizer, f'/api/groups/{group_id}/profile', {'alias': 'Alice'})
        self.post(self.member, f'/api/groups/{group_id}/profile', {'alias': 'Bob'})

        offers = self.organizer.get('/api/catalog/offers?domain=movie').json['offers']
        target_offer = offers[0]
        seat_ids = [target_offer['resources'][0]['id'], target_offer['resources'][1]['id']]

        self.post(self.organizer, f'/api/groups/{group_id}/freeze', {
            'offerID': target_offer['id'],
            'resourceIDs': seat_ids
        })

        # Member views booking
        member_view = self.member.get(f'/api/groups/{group_id}/booking').json
        self.assertTrue(member_view['hasBooking'])
        self.assertEqual(member_view['myShare']['alias'], 'Bob')
        self.assertEqual(member_view['myShare']['shareValue'], '16.00')
        self.assertFalse(member_view['isOrganizer'])

        # Progress shows coarse progress only
        self.assertEqual(len(member_view['rosterProgress']), 2)
        aliases = [p['alias'] for p in member_view['rosterProgress']]
        self.assertIn('Alice', aliases)
        self.assertIn('Bob', aliases)

        # Outsider receives 404
        outsider_resp = self.outsider.get(f'/api/groups/{group_id}/booking')
        self.assertEqual(outsider_resp.status_code, 404)

    def test_member_consent_flow(self):
        group_id = self.create_group_with_member()
        offers = self.organizer.get('/api/catalog/offers?domain=movie').json['offers']
        target_offer = offers[0]
        seat_ids = [target_offer['resources'][0]['id'], target_offer['resources'][1]['id']]

        self.post(self.organizer, f'/api/groups/{group_id}/freeze', {
            'offerID': target_offer['id'],
            'resourceIDs': seat_ids
        })

        # Member gives consent
        consent_resp = self.post(self.member, f'/api/groups/{group_id}/booking/consent', {})
        self.assertEqual(consent_resp.status_code, 200)
        self.assertTrue(consent_resp.json['myShare']['consentGiven'])
        self.assertEqual(consent_resp.json['myShare']['state'], 'ACCEPTED')

    def test_schema_migration_revision_two_to_three(self):
        path = Path(self.directory.name) / 'migration_test.db'
        store = Store('sqlite:///' + path.as_posix())
        # Simulate an existing database at revision 2
        for table in (versions, participants, workshops, bookings, attempts, entitlements,
                      workshop_groups, group_memberships):
            table.create(store.engine)
        with store.engine.begin() as connection:
            connection.execute(insert(versions).values(id=1, revision=2))
            connection.execute(insert(participants).values(
                id='mig_prior', token_hash='hash_prior', csrf_token='csrf_prior', expires_at=9999999999))

        # Perform migration to revision 3
        store.migrate(target=3)
        with store.engine.connect() as connection:
            self.assertEqual(connection.execute(select(versions.c.revision)).scalar_one(), 3)
            self.assertEqual(connection.execute(select(participants.c.id)).scalar_one(), 'mig_prior')

        # Check new tables exist
        table_names = inspect(store.engine).get_table_names()
        self.assertIn('catalog_offers', table_names)
        self.assertIn('catalog_resources', table_names)
        self.assertIn('shared_purchases', table_names)
        self.assertIn('purchase_contributions', table_names)
        store.engine.dispose()


if __name__ == '__main__':
    unittest.main()
