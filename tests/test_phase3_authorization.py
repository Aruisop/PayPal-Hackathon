"""Tests for Phase 3: Reservation holds, group-specific contributions, AUTHORIZE intent, and void/recovery."""
import tempfile
import time
import unittest
from pathlib import Path

from app import create_app
from app.shared.storage import catalog_resources, purchase_contributions, shared_purchases
from test_workshop_slice import FakePayPal


class Phase3AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.fake = FakePayPal()
        self.config = dict(
            DATABASE_URL='sqlite:///' + (Path(self.directory.name) / 'phase3.db').as_posix(),
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

    def create_frozen_group(self):
        created = self.post(self.organizer, '/api/groups', {'name': 'Friday Movie'}).json
        invite_token = created['inviteURL'].split('invite=', 1)[1]
        self.post(self.member, '/api/groups/join', {'inviteToken': invite_token})

        self.post(self.organizer, f'/api/groups/{created["id"]}/profile', {'alias': 'Alice'})
        self.post(self.member, f'/api/groups/{created["id"]}/profile', {'alias': 'Bob'})

        # Freeze with Cosmic Odyssey (2 seats: res-movie-cosmic-odyssey-fri-A1, A2)
        freeze_resp = self.post(self.organizer, f'/api/groups/{created["id"]}/freeze', {
            'offerID': 'movie-cosmic-odyssey-fri',
            'resourceIDs': ['res-movie-cosmic-odyssey-fri-A1', 'res-movie-cosmic-odyssey-fri-A2']
        })
        self.assertEqual(freeze_resp.status_code, 200)
        return created['id']

    def test_consent_required_before_order_creation(self):
        group_id = self.create_frozen_group()
        # Attempting order before consent fails
        resp = self.post(self.member, f'/api/groups/{group_id}/contributions/order', {})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json['error'], 'CONSENT_REQUIRED')

        # Give consent succeeds
        consent_resp = self.post(self.member, f'/api/groups/{group_id}/booking/consent', {})
        self.assertEqual(consent_resp.status_code, 200)

        # Now order creation succeeds
        order_resp = self.post(self.member, f'/api/groups/{group_id}/contributions/order', {})
        self.assertEqual(order_resp.status_code, 200)
        self.assertTrue(order_resp.json['orderID'].startswith('ORDER'))
        self.assertEqual(order_resp.json['shareCents'], 1600)
        self.assertEqual(order_resp.json['currency'], 'USD')

    def test_authorize_intent_and_server_owned_share(self):
        group_id = self.create_frozen_group()
        self.post(self.organizer, f'/api/groups/{group_id}/booking/consent', {})
        self.post(self.organizer, f'/api/groups/{group_id}/contributions/order', {})

        # Verify in FakePayPal that the order had intent='AUTHORIZE'
        order = list(self.fake.orders.values())[0]
        self.assertEqual(order['intent'], 'AUTHORIZE')
        self.assertEqual(order['purchase_units'][0]['amount']['value'], '16.00')

    def test_repeated_order_initiation_idempotent(self):
        group_id = self.create_frozen_group()
        self.post(self.organizer, f'/api/groups/{group_id}/booking/booking' if False else f'/api/groups/{group_id}/booking/consent', {})
        resp1 = self.post(self.organizer, f'/api/groups/{group_id}/contributions/order', {}).json
        resp2 = self.post(self.organizer, f'/api/groups/{group_id}/contributions/order', {}).json
        self.assertEqual(resp1['orderID'], resp2['orderID'])

    def test_successful_authorization_held_funds_no_ticket(self):
        group_id = self.create_frozen_group()
        self.post(self.organizer, f'/api/groups/{group_id}/booking/consent', {})
        order_info = self.post(self.organizer, f'/api/groups/{group_id}/contributions/order', {}).json
        self.fake.approve(order_info['orderID'])

        # Authorize share
        auth_resp = self.post(self.organizer, f'/api/groups/{group_id}/contributions/authorize', {})
        self.assertEqual(auth_resp.status_code, 200)
        data = auth_resp.json
        self.assertEqual(data['myShare']['state'], 'AUTHORIZED')
        self.assertTrue(data['myShare']['authorizationID'].startswith('AUTH'))

        # PRD Section 10 exit gate check: held funds only, NO ticket issued!
        self.assertNotIn('ticket', str(data).lower())
        self.assertNotIn('tickets', data)

    def test_all_members_authorized_transitions_to_finalizing(self):
        group_id = self.create_frozen_group()

        # Alice consents and authorizes
        self.post(self.organizer, f'/api/groups/{group_id}/booking/consent', {})
        ord1 = self.post(self.organizer, f'/api/groups/{group_id}/contributions/order', {}).json
        self.fake.approve(ord1['orderID'])
        v1 = self.post(self.organizer, f'/api/groups/{group_id}/contributions/authorize', {}).json
        self.assertEqual(v1['state'], 'AWAITING_AUTHORIZATIONS')

        # Bob consents and authorizes
        self.post(self.member, f'/api/groups/{group_id}/booking/consent', {})
        ord2 = self.post(self.member, f'/api/groups/{group_id}/contributions/order', {}).json
        self.fake.approve(ord2['orderID'])
        v2 = self.post(self.member, f'/api/groups/{group_id}/contributions/authorize', {}).json

        # All authorized -> FINALIZING
        self.assertEqual(v2['state'], 'FINALIZING')

    def test_expired_hold_deadline_rejects_authorization(self):
        group_id = self.create_frozen_group()
        self.post(self.organizer, f'/api/groups/{group_id}/booking/consent', {})
        ord_res = self.post(self.organizer, f'/api/groups/{group_id}/contributions/order', {}).json
        self.fake.approve(ord_res['orderID'])

        # Manually expire hold deadline in database
        store = self.app.extensions['store']
        with store.engine.begin() as conn:
            conn.execute(shared_purchases.update().values(hold_deadline=time.time() - 100))

        # Authorization should be rejected
        resp = self.post(self.organizer, f'/api/groups/{group_id}/contributions/authorize', {})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json['error'], 'HOLD_DEADLINE_EXPIRED')

    def test_void_releases_held_seats_and_voids_authorization(self):
        group_id = self.create_frozen_group()
        self.post(self.organizer, f'/api/groups/{group_id}/booking/consent', {})
        ord1 = self.post(self.organizer, f'/api/groups/{group_id}/contributions/order', {}).json
        self.fake.approve(ord1['orderID'])
        self.post(self.organizer, f'/api/groups/{group_id}/contributions/authorize', {})

        # Void booking
        void_resp = self.post(self.organizer, f'/api/groups/{group_id}/booking/void', {})
        self.assertEqual(void_resp.status_code, 200)
        self.assertEqual(void_resp.json['state'], 'CANCELLED')

        # Check seats released back to FREE in catalog_resources
        store = self.app.extensions['store']
        with store.engine.connect() as conn:
            from sqlalchemy import select
            res_states = conn.execute(select(catalog_resources.c.state).where(
                catalog_resources.c.id.in_(['res-movie-cosmic-odyssey-fri-A1', 'res-movie-cosmic-odyssey-fri-A2'])
            )).scalars().all()
            self.assertTrue(all(s == 'FREE' for s in res_states))

        # Check authorization was voided on provider
        self.assertEqual(getattr(self.fake, 'void_calls', 0), 1)

    def test_interrupted_authorization_recovered_via_reconcile(self):
        group_id = self.create_frozen_group()
        self.post(self.organizer, f'/api/groups/{group_id}/booking/consent', {})
        ord1 = self.post(self.organizer, f'/api/groups/{group_id}/contributions/order', {}).json
        self.fake.approve(ord1['orderID'])

        # Simulate provider created authorization, but connection dropped before response returned
        self.fake.lose_authorize_response = True
        fail_resp = self.post(self.organizer, f'/api/groups/{group_id}/contributions/authorize', {})
        self.assertEqual(fail_resp.status_code, 502)

        # Call reconcile
        self.fake.lose_authorize_response = False
        rec_resp = self.post(self.organizer, f'/api/groups/{group_id}/contributions/reconcile', {})
        self.assertEqual(rec_resp.status_code, 200)
        self.assertEqual(rec_resp.json['myShare']['state'], 'AUTHORIZED')
        self.assertTrue(rec_resp.json['myShare']['authorizationID'].startswith('AUTH'))

    def test_cross_participant_isolation_cannot_access_or_order_other_share(self):
        group_id = self.create_frozen_group()
        # Outsider cannot order share in group
        resp = self.post(self.outsider, f'/api/groups/{group_id}/contributions/order', {})
        self.assertEqual(resp.status_code, 404)

    def test_simulation_endpoints_cannot_mark_real_contributions_authorized(self):
        group_id = self.create_frozen_group()
        for path in ('simulate-authorizations', 'preflight-reserve', 'members/add-demo'):
            response = self.post(self.organizer, f'/api/groups/{group_id}/{path}', {})
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.organizer.get(f'/api/groups/{group_id}/liquidity-profiles').status_code, 404)
        saved = self.organizer.get(f'/api/groups/{group_id}/booking').json
        self.assertEqual(saved['state'], 'AWAITING_AUTHORIZATIONS')
        self.assertTrue(all(not row['hasAuthorized'] for row in saved['rosterProgress']))
