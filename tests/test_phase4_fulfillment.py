"""Tests for Phase 4: Sequential capture coordinator, private ticket issuance, and partial-failure refund recovery."""
import tempfile
import unittest
from pathlib import Path

from server import create_app
from storage import catalog_resources, group_operations, group_tickets
from test_workshop_slice import FakePayPal


class Phase4FulfillmentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.fake = FakePayPal()
        self.config = dict(
            DATABASE_URL='sqlite:///' + (Path(self.directory.name) / 'phase4.db').as_posix(),
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

    def create_authorized_group(self):
        # Create group and join
        created = self.post(self.organizer, '/api/groups', {'name': 'Movie Squad'}).json
        invite_token = created['inviteURL'].split('invite=', 1)[1]
        self.post(self.member, '/api/groups/join', {'inviteToken': invite_token})

        self.post(self.organizer, f'/api/groups/{created["id"]}/profile', {'alias': 'Alice'})
        self.post(self.member, f'/api/groups/{created["id"]}/profile', {'alias': 'Bob'})

        # Freeze roster with Cosmic Odyssey
        self.post(self.organizer, f'/api/groups/{created["id"]}/freeze', {
            'offerID': 'movie-cosmic-odyssey-fri',
            'resourceIDs': ['res-movie-cosmic-odyssey-fri-A1', 'res-movie-cosmic-odyssey-fri-A2']
        })

        # Alice consents, orders, approves, authorizes
        self.post(self.organizer, f'/api/groups/{created["id"]}/booking/consent', {})
        ord1 = self.post(self.organizer, f'/api/groups/{created["id"]}/contributions/order', {}).json
        self.fake.approve(ord1['orderID'])
        self.post(self.organizer, f'/api/groups/{created["id"]}/contributions/authorize', {})

        # Bob consents, orders, approves, authorizes
        self.post(self.member, f'/api/groups/{created["id"]}/booking/consent', {})
        ord2 = self.post(self.member, f'/api/groups/{created["id"]}/contributions/order', {}).json
        self.fake.approve(ord2['orderID'])
        self.post(self.member, f'/api/groups/{created["id"]}/contributions/authorize', {})

        return created['id']

    def test_successful_end_to_end_finalization_and_ticket_issuance(self):
        group_id = self.create_authorized_group()

        # Finalize booking
        fin_resp = self.post(self.organizer, f'/api/groups/{group_id}/finalize', {})
        self.assertEqual(fin_resp.status_code, 200)
        self.assertEqual(fin_resp.json['state'], 'CONFIRMED')

        # Check seats are now BOOKED
        store = self.app.extensions['store']
        with store.engine.connect() as conn:
            from sqlalchemy import select
            states = conn.execute(select(catalog_resources.c.state).where(
                catalog_resources.c.id.in_(['res-movie-cosmic-odyssey-fri-A1', 'res-movie-cosmic-odyssey-fri-A2'])
            )).scalars().all()
            self.assertTrue(all(s == 'BOOKED' for s in states))

        # Check tickets were issued in database
        with store.engine.connect() as conn:
            tickets = conn.execute(select(group_tickets)).mappings().all()
            self.assertEqual(len(tickets), 2)

    def test_private_ticket_isolation(self):
        group_id = self.create_authorized_group()
        self.post(self.organizer, f'/api/groups/{group_id}/finalize', {})

        # Alice fetches her ticket
        t1 = self.organizer.get(f'/api/groups/{group_id}/ticket').json
        self.assertTrue(t1['ticketCode'].startswith('TICKET-'))
        self.assertEqual(t1['alias'], 'Alice')
        self.assertEqual(t1['assignedResource'], 'Seat A1')

        # Bob fetches his ticket
        t2 = self.member.get(f'/api/groups/{group_id}/ticket').json
        self.assertTrue(t2['ticketCode'].startswith('TICKET-'))
        self.assertEqual(t2['alias'], 'Bob')
        self.assertEqual(t2['assignedResource'], 'Seat A2')

        # Tickets are private and distinct
        self.assertNotEqual(t1['ticketCode'], t2['ticketCode'])

        # Outsider cannot view tickets
        outsider_resp = self.outsider.get(f'/api/groups/{group_id}/ticket')
        self.assertEqual(outsider_resp.status_code, 404)

    def test_partial_capture_failure_triggers_immediate_refunds_and_voids(self):
        group_id = self.create_authorized_group()

        # Let the first capture succeed, but make the second capture fail!
        call_count = 0
        original_capture = self.fake.capture_authorization

        def fail_on_second(auth_id, payload, req_id):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                self.fake.reject_capture_auth = True
            return original_capture(auth_id, payload, req_id)

        self.fake.capture_authorization = fail_on_second

        # Finalize should encounter partial capture failure and execute compensatory recovery
        fin_resp = self.post(self.organizer, f'/api/groups/{group_id}/finalize', {})
        self.assertEqual(fin_resp.status_code, 502)
        self.assertEqual(fin_resp.json['error'], 'PAYMENT_RECOVERY_REQUIRED')
        saved = self.organizer.get(f'/api/groups/{group_id}/booking').json
        self.assertEqual(saved['state'], 'CANCELLED')

        # Verify refund was executed for the completed capture
        self.assertEqual(self.fake.refund_calls, 1)

        # Verify held resources are released back to FREE
        store = self.app.extensions['store']
        with store.engine.connect() as conn:
            from sqlalchemy import select
            states = conn.execute(select(catalog_resources.c.state).where(
                catalog_resources.c.id.in_(['res-movie-cosmic-odyssey-fri-A1', 'res-movie-cosmic-odyssey-fri-A2'])
            )).scalars().all()
            self.assertTrue(all(s == 'FREE' for s in states))

        # Verify NO tickets were issued
        with store.engine.connect() as conn:
            tickets = conn.execute(select(group_tickets)).scalars().all()
            self.assertEqual(len(tickets), 0)

        # Verify recovery tasks were recorded
        with store.engine.connect() as conn:
            tasks = conn.execute(select(group_operations).where(group_operations.c.kind.in_(['REFUND', 'VOID']))).mappings().all()
            self.assertGreaterEqual(len(tasks), 1)

    def test_finalize_rejected_if_not_all_members_authorized(self):
        # Create group with only Alice authorized
        created = self.post(self.organizer, '/api/groups', {'name': 'Movie Squad'}).json
        invite_token = created['inviteURL'].split('invite=', 1)[1]
        self.post(self.member, '/api/groups/join', {'inviteToken': invite_token})
        self.post(self.organizer, f'/api/groups/{created["id"]}/profile', {'alias': 'Alice'})
        self.post(self.member, f'/api/groups/{created["id"]}/profile', {'alias': 'Bob'})

        self.post(self.organizer, f'/api/groups/{created["id"]}/freeze', {
            'offerID': 'movie-cosmic-odyssey-fri',
            'resourceIDs': ['res-movie-cosmic-odyssey-fri-A1', 'res-movie-cosmic-odyssey-fri-A2']
        })

        # Alice authorizes
        self.post(self.organizer, f'/api/groups/{created["id"]}/booking/consent', {})
        ord1 = self.post(self.organizer, f'/api/groups/{created["id"]}/contributions/order', {}).json
        self.fake.approve(ord1['orderID'])
        self.post(self.organizer, f'/api/groups/{created["id"]}/contributions/authorize', {})

        # Bob has NOT authorized yet -> finalize rejected
        fin_resp = self.post(self.organizer, f'/api/groups/{created["id"]}/finalize', {})
        self.assertEqual(fin_resp.status_code, 400)
        self.assertEqual(fin_resp.json['error'], 'ALL_AUTHORIZATIONS_REQUIRED')
