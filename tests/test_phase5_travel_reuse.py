"""Tests for Phase 5: Reusing coordinator for travel domain (fixed-price excursions and place assignments)."""
import tempfile
import unittest
from pathlib import Path

from server import create_app
from storage import catalog_resources, group_tickets
from test_workshop_slice import FakePayPal


class Phase5TravelReuseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.fake = FakePayPal()
        self.config = dict(
            DATABASE_URL='sqlite:///' + (Path(self.directory.name) / 'phase5.db').as_posix(),
            APP_ORIGIN='http://localhost',
            COOKIE_SECURE=False,
            APP_ENV='development',
            TESTING=True
        )
        self.app = create_app(self.config, paypal=self.fake)
        self.organizer = self.app.test_client()
        self.member1 = self.app.test_client()
        self.member2 = self.app.test_client()
        self.csrf = {client: client.get('/api/config').json['csrfToken']
                     for client in (self.organizer, self.member1, self.member2)}

    def tearDown(self):
        self.app.extensions['store'].engine.dispose()
        self.directory.cleanup()

    def post(self, client, path, body):
        return client.post(path, json=body, headers={
            'Origin': 'http://localhost',
            'X-CSRF-Token': self.csrf[client]
        })

    def create_three_person_excursion_group(self):
        created = self.post(self.organizer, '/api/groups', {'name': 'River Kayak Crew'}).json
        invite_token = created['inviteURL'].split('invite=', 1)[1]
        self.post(self.member1, '/api/groups/join', {'inviteToken': invite_token})
        self.post(self.member2, '/api/groups/join', {'inviteToken': invite_token})

        self.post(self.organizer, f'/api/groups/{created["id"]}/profile', {'alias': 'Alice'})
        self.post(self.member1, f'/api/groups/{created["id"]}/profile', {'alias': 'Bob'})
        self.post(self.member2, f'/api/groups/{created["id"]}/profile', {'alias': 'Charlie'})
        return created['id']

    def test_excursion_fixed_price_three_member_split(self):
        group_id = self.create_three_person_excursion_group()
        # Emerald River Kayak is $100.00 (10000 cents) fixed group price
        quote_resp = self.post(self.organizer, f'/api/groups/{group_id}/quote', {
            'offerID': 'excursion-kayak-canyon-sat'
        })
        self.assertEqual(quote_resp.status_code, 200)
        q = quote_resp.json
        self.assertEqual(q['totalCents'], 10000)
        self.assertEqual(q['totalValue'], '100.00')

        # PRD Section 10 exit gate check: $100/3 gives $33.34, $33.33, $33.33
        shares = [s['shareCents'] for s in q['shares']]
        self.assertEqual(shares, [3334, 3333, 3333])
        self.assertEqual(sum(shares), 10000)

    def test_excursion_freeze_authorization_and_fulfillment(self):
        group_id = self.create_three_person_excursion_group()

        # Organizer freezes excursion with 3 places
        freeze_resp = self.post(self.organizer, f'/api/groups/{group_id}/freeze', {
            'offerID': 'excursion-kayak-canyon-sat',
            'resourceIDs': ['res-excursion-kayak-canyon-sat-P1',
                            'res-excursion-kayak-canyon-sat-P2',
                            'res-excursion-kayak-canyon-sat-P3']
        })
        self.assertEqual(freeze_resp.status_code, 200)
        self.assertEqual(freeze_resp.json['state'], 'AWAITING_AUTHORIZATIONS')

        # All 3 members consent, order, and authorize
        clients = [self.organizer, self.member1, self.member2]
        expected_shares = [3334, 3333, 3333]
        for idx, client in enumerate(clients):
            self.post(client, f'/api/groups/{group_id}/booking/consent', {})
            order_data = self.post(client, f'/api/groups/{group_id}/contributions/order', {}).json
            self.assertEqual(order_data['shareCents'], expected_shares[idx])
            self.fake.approve(order_data['orderID'])
            auth_data = self.post(client, f'/api/groups/{group_id}/contributions/authorize', {}).json

        # After all 3 authorize, booking state is FINALIZING
        self.assertEqual(auth_data['state'], 'FINALIZING')

        # Finalize excursion
        fin_resp = self.post(self.organizer, f'/api/groups/{group_id}/finalize', {})
        self.assertEqual(fin_resp.status_code, 200)
        self.assertEqual(fin_resp.json['state'], 'CONFIRMED')

        # Check tickets issued for all 3 participants
        t1 = self.organizer.get(f'/api/groups/{group_id}/ticket').json
        t2 = self.member1.get(f'/api/groups/{group_id}/ticket').json
        t3 = self.member2.get(f'/api/groups/{group_id}/ticket').json

        self.assertEqual(t1['assignedResource'], 'Place #1')
        self.assertEqual(t1['shareCents'], 3334)
        self.assertEqual(t2['assignedResource'], 'Place #2')
        self.assertEqual(t2['shareCents'], 3333)
        self.assertEqual(t3['assignedResource'], 'Place #3')
        self.assertEqual(t3['shareCents'], 3333)

        self.assertTrue(t1['ticketCode'].startswith('TICKET-excursion-kayak-canyon-sat'))
        self.assertTrue(t2['ticketCode'].startswith('TICKET-excursion-kayak-canyon-sat'))
        self.assertTrue(t3['ticketCode'].startswith('TICKET-excursion-kayak-canyon-sat'))

        # Check places are BOOKED in catalog_resources
        store = self.app.extensions['store']
        with store.engine.connect() as conn:
            from sqlalchemy import select
            states = conn.execute(select(catalog_resources.c.state).where(
                catalog_resources.c.id.in_([
                    'res-excursion-kayak-canyon-sat-P1',
                    'res-excursion-kayak-canyon-sat-P2',
                    'res-excursion-kayak-canyon-sat-P3'
                ])
            )).scalars().all()
            self.assertTrue(all(s == 'BOOKED' for s in states))
