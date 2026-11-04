"""Focused merchant checkout coverage; provider operations remain fake."""
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.shared.storage import versions
from test_workshop_slice import FakePayPal


class MerchantCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.fake = FakePayPal()
        self.app = create_app(dict(
            DATABASE_URL='sqlite:///' + (Path(self.directory.name) / 'merchant.db').as_posix(),
            APP_ORIGIN='http://localhost', COOKIE_SECURE=False, APP_ENV='development', TESTING=True
        ), paypal=self.fake)
        self.owner, self.friend, self.extra = self.app.test_client(), self.app.test_client(), self.app.test_client()
        self.csrf = {client: client.get('/api/config').json['csrfToken'] for client in (self.owner, self.friend, self.extra)}

    def tearDown(self):
        self.app.extensions['store'].engine.dispose()
        self.directory.cleanup()

    def post(self, client, path, body):
        return client.post(path, json=body, headers={'Origin': 'http://localhost', 'X-CSRF-Token': self.csrf[client]})

    def test_merchant_roster_is_fixed_before_hold_and_equal_split_is_server_owned(self):
        created = self.post(self.owner, '/api/merchant-checkouts', {
            'offerID': 'movie-cosmic-odyssey-fri', 'payerCount': 2
        })
        self.assertEqual(created.status_code, 200)
        group = created.json
        self.assertEqual(group['merchantCheckout']['targetMemberCount'], 2)
        self.assertEqual(self.post(self.owner, f"/api/groups/{group['id']}/merchant-freeze", {}).json['error'], 'MERCHANT_ROSTER_INCOMPLETE')
        token = group['inviteURL'].split('invite=', 1)[1]
        self.assertEqual(self.post(self.friend, '/api/groups/join', {'inviteToken': token}).status_code, 200)
        self.assertEqual(self.post(self.extra, '/api/groups/join', {'inviteToken': token}).json['error'], 'GROUP_MAX_CAPACITY')
        frozen = self.post(self.owner, f"/api/groups/{group['id']}/merchant-freeze", {})
        self.assertEqual(frozen.status_code, 200)
        self.assertEqual(frozen.json['totalCents'], 3200)
        self.assertEqual(frozen.json['myShare']['shareCents'], 1600)

    def test_one_payer_uses_the_same_verified_authorize_capture_path(self):
        created = self.post(self.owner, '/api/merchant-checkouts', {
            'offerID': 'movie-cosmic-odyssey-fri', 'payerCount': 1
        }).json
        group_id = created['id']
        self.assertEqual(self.post(self.owner, f'/api/groups/{group_id}/merchant-freeze', {}).status_code, 200)
        self.assertEqual(self.post(self.owner, f'/api/groups/{group_id}/booking/consent', {}).status_code, 200)
        order = self.post(self.owner, f'/api/groups/{group_id}/contributions/order', {}).json
        self.assertEqual(order['shareCents'], 1600)
        self.assertEqual(self.fake.orders[order['orderID']]['intent'], 'AUTHORIZE')
        self.fake.approve(order['orderID'])
        self.assertEqual(self.post(self.owner, f'/api/groups/{group_id}/contributions/authorize', {}).json['state'], 'FINALIZING')
        self.assertEqual(self.post(self.owner, f'/api/groups/{group_id}/finalize', {}).json['state'], 'CONFIRMED')

    def test_merchant_checkout_revision_is_applied_additively(self):
        with self.app.extensions['store'].engine.connect() as connection:
            self.assertEqual(connection.execute(versions.select()).mappings().one()['revision'], 6)


if __name__ == '__main__':
    unittest.main()
