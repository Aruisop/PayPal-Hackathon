import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from server import Checkout, Handler, PayPal, PayPalError, PRODUCT


class FakePayPal:
    client_id = 'public-client-id'
    secret = 'never-expose-this-secret'

    def __init__(self):
        self.calls = []
        self.fail_once = False

    def order_request(self, path, payload, request_id, decline=False):
        self.calls.append((path, payload, request_id, decline))
        if path.endswith('/capture'):
            if decline:
                raise PayPalError('INSTRUMENT_DECLINED', 'test-debug-id', 422)
            if self.fail_once:
                self.fail_once = False
                raise PayPalError('PAYPAL_UNAVAILABLE')
            return {'purchase_units': [{'payments': {'captures': [{
                'id': 'CAPTURE123', 'status': 'COMPLETED',
                'amount': {'currency_code': 'USD', 'value': '25.00'},
            }]}}]}
        return {'id': 'ORDER123'}


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.paypal = FakePayPal()
        self.checkout = Checkout(self.paypal)

    def test_price_and_capture_retry_idempotency(self):
        order = self.checkout.create('buyer')
        self.assertEqual(self.paypal.calls[0][1]['purchase_units'][0]['amount']['value'], PRODUCT['value'])
        self.paypal.fail_once = True
        with self.assertRaises(PayPalError):
            self.checkout.capture('buyer', order['id'])
        result = self.checkout.capture('buyer', order['id'])
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertEqual(self.paypal.calls[1][2], self.paypal.calls[2][2])
        self.assertEqual(self.checkout.capture('buyer', order['id']), result)
        self.assertEqual(len(self.paypal.calls), 3)

    def test_other_session_cannot_capture(self):
        self.checkout.create('buyer')
        with self.assertRaises(PayPalError) as raised:
            self.checkout.capture('other-buyer', 'ORDER123')
        self.assertEqual(raised.exception.status, 404)
        self.assertEqual(len(self.paypal.calls), 1)

    def test_decline_returns_issue_and_debug_reference(self):
        self.checkout.create('buyer', decline=True)
        with self.assertRaises(PayPalError) as raised:
            self.checkout.capture('buyer', 'ORDER123')
        self.assertEqual(raised.exception.issue, 'INSTRUMENT_DECLINED')
        self.assertEqual(raised.exception.debug_id, 'test-debug-id')
        self.assertTrue(self.paypal.calls[-1][3])

    def test_real_adapter_adds_sandbox_mock_header(self):
        paypal = PayPal('id', 'secret')
        with patch.object(paypal, 'access_token', return_value='token'), patch.object(paypal, 'request', return_value={}) as request:
            paypal.order_request('/v2/checkout/orders/ORDER123/capture', {}, 'retry-key', True)
        headers = request.call_args.args[2]
        self.assertEqual(json.loads(headers['PayPal-Mock-Response'])['mock_application_codes'], 'INSTRUMENT_DECLINED')
        self.assertEqual(headers['PayPal-Request-Id'], 'retry-key')


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Handler.checkout = Checkout(FakePayPal())
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_http_flow_and_secret_privacy(self):
        with urllib.request.urlopen(self.url + '/api/config') as response:
            config = response.read().decode()
            cookie = response.headers['Set-Cookie'].split(';')[0]
        self.assertNotIn('never-expose-this-secret', config)
        headers = {'Origin': self.url, 'Cookie': cookie, 'Content-Type': 'application/json'}
        request = urllib.request.Request(self.url + '/api/orders', data=b'{"value":"0.01"}', headers=headers)
        with urllib.request.urlopen(request) as response:
            self.assertEqual(json.load(response)['id'], 'ORDER123')
        request = urllib.request.Request(self.url + '/api/orders/ORDER123/capture', data=b'{}', headers=headers)
        with urllib.request.urlopen(request) as response:
            self.assertEqual(json.load(response)['amount']['value'], '25.00')

    def test_cross_origin_rejected(self):
        request = urllib.request.Request(self.url + '/api/orders', data=b'{}', headers={'Origin': 'https://example.com'})
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request)
        self.assertEqual(raised.exception.code, 403)

    def test_static_routes_and_traversal(self):
        for path in ('/', '/app.js', '/style.css'):
            with urllib.request.urlopen(self.url + path) as response:
                self.assertEqual(response.status, 200)
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(self.url + '/../.env')
        self.assertEqual(raised.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
