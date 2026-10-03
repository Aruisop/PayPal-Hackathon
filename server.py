"""Local PayPal Sandbox checkout demo. Python 3.10+, no dependencies."""
import base64
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = 'https://api-m.sandbox.paypal.com'
PRODUCT = {'name': 'Weekend explorer kit', 'value': '25.00', 'currency': 'USD'}


def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


class PayPalError(Exception):
    def __init__(self, issue, debug_id='', status=502):
        self.issue, self.debug_id, self.status = issue, debug_id, status


class PayPal:
    def __init__(self, client_id, secret):
        self.client_id, self.secret = client_id, secret
        self.token, self.expires = '', 0

    def request(self, path, payload=None, headers=None, form=None):
        body = form.encode() if form else json.dumps(payload).encode()
        request = urllib.request.Request(BASE + path, data=body, headers=headers or {}, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                data = json.loads(error.read())
            except (ValueError, UnicodeDecodeError):
                data = {}
            issue = (data.get('details') or [{}])[0].get('issue') or data.get('error') or data.get('name') or 'PAYPAL_ERROR'
            raise PayPalError(issue, data.get('debug_id', ''), 422 if error.code == 422 else 502) from error
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            raise PayPalError('PAYPAL_UNAVAILABLE') from error

    def access_token(self):
        if time.time() >= self.expires:
            basic = base64.b64encode(f'{self.client_id}:{self.secret}'.encode()).decode()
            data = self.request('/v1/oauth2/token', headers={
                'Authorization': 'Basic ' + basic,
                'Content-Type': 'application/x-www-form-urlencoded',
            }, form='grant_type=client_credentials')
            self.token = data['access_token']
            self.expires = time.time() + int(data['expires_in']) - 60
        return self.token

    def order_request(self, path, payload, request_id, decline=False):
        headers = {'Authorization': 'Bearer ' + self.access_token(),
                   'Content-Type': 'application/json', 'PayPal-Request-Id': request_id}
        if decline:
            headers['PayPal-Mock-Response'] = json.dumps({'mock_application_codes': 'INSTRUMENT_DECLINED'})
        return self.request(path, payload, headers)


class Checkout:
    def __init__(self, paypal):
        self.paypal = paypal
        self.orders = {}
        self.lock = threading.Lock()

    def create(self, session, decline=False):
        # Serialize the small local demo's requests, including capture retries.
        with self.lock:
            self.orders = {key: value for key, value in self.orders.items() if value['expires'] > time.time()}
            if len(self.orders) >= 500:
                raise PayPalError('TOO_MANY_ORDERS', status=429)
            data = self.paypal.order_request('/v2/checkout/orders', {
                'intent': 'CAPTURE', 'purchase_units': [{
                    'description': PRODUCT['name'],
                    'amount': {'currency_code': PRODUCT['currency'], 'value': PRODUCT['value']},
                }],
            }, secrets.token_hex(16))
            order_id = data['id']
            self.orders[order_id] = {'session': session, 'decline': decline,
                                     'capture_key': secrets.token_hex(16), 'result': None,
                                     'expires': time.time() + 3600}
            return {'id': order_id}

    def capture(self, session, order_id):
        with self.lock:
            order = self.orders.get(order_id)
            if not order or order['session'] != session or order['expires'] <= time.time():
                raise PayPalError('ORDER_NOT_FOUND', status=404)
            if order['result']:
                return order['result']
            data = self.paypal.order_request(f'/v2/checkout/orders/{order_id}/capture', {},
                                             order['capture_key'], order['decline'])
            captures = [capture for unit in data.get('purchase_units', [])
                        for capture in unit.get('payments', {}).get('captures', [])]
            if not captures:
                raise PayPalError('CAPTURE_NOT_CONFIRMED')
            capture = captures[0]
            if capture.get('amount') != {'currency_code': PRODUCT['currency'], 'value': PRODUCT['value']}:
                raise PayPalError('CAPTURE_AMOUNT_MISMATCH')
            result = {'orderID': order_id, 'captureID': capture['id'],
                      'status': capture['status'], 'amount': capture['amount']}
            order['result'] = result
            return result


class Handler(BaseHTTPRequestHandler):
    checkout = None

    def send(self, status, data, content_type='application/json', cookie=None):
        body = json.dumps(data).encode() if content_type == 'application/json' else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        if cookie:
            self.send_header('Set-Cookie', f'checkout_session={cookie}; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()
        self.wfile.write(body)

    def session(self):
        cookie = self.headers.get('Cookie', '')
        match = re.search(r'(?:^|;\s*)checkout_session=([a-f0-9]{48})(?:;|$)', cookie)
        return match.group(1) if match else None

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == '/api/config':
            session = self.session() or secrets.token_hex(24)
            self.send(200, {'clientID': self.checkout.paypal.client_id,
                            'configured': bool(self.checkout.paypal.client_id and self.checkout.paypal.secret),
                            'product': PRODUCT}, cookie=session)
        elif path in ('/', '/app.js', '/style.css'):
            name, content_type = {'/': ('index.html', 'text/html; charset=utf-8'),
                                  '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                                  '/style.css': ('style.css', 'text/css; charset=utf-8')}[path]
            self.send(200, (ROOT / 'public' / name).read_bytes(), content_type)
        else:
            self.send(404, {'error': 'NOT_FOUND'})

    def do_POST(self):
        # Local-only server; reject cross-origin browser writes and missing sessions.
        if self.headers.get('Origin') != f'http://{self.headers.get("Host")}' or not self.session():
            return self.send(403, {'error': 'INVALID_ORIGIN_OR_SESSION'})
        if not self.checkout.paypal.client_id or not self.checkout.paypal.secret:
            return self.send(503, {'error': 'CREDENTIALS_MISSING'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 0 or size > 4096:
                return self.send(413, {'error': 'REQUEST_TOO_LARGE'})
            body = json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(body, dict):
                raise ValueError()
            if self.path == '/api/orders':
                if body.get('scenario', 'success') not in ('success', 'decline'):
                    raise ValueError()
                result = self.checkout.create(self.session(), body.get('scenario') == 'decline')
                self.send(201, result)
            elif re.fullmatch(r'/api/orders/[A-Za-z0-9]+/capture', self.path):
                self.send(200, self.checkout.capture(self.session(), self.path.split('/')[3]))
            else:
                self.send(404, {'error': 'NOT_FOUND'})
        except (ValueError, UnicodeDecodeError):
            self.send(400, {'error': 'INVALID_REQUEST'})
        except PayPalError as error:
            print(f'PayPal issue={error.issue} debug_id={error.debug_id}', flush=True)
            self.send(error.status, {'error': error.issue, 'debugID': error.debug_id})
        except Exception:
            self.send(502, {'error': 'UNEXPECTED_RESPONSE'})


if __name__ == '__main__':
    load_env()
    Handler.checkout = Checkout(PayPal(os.getenv('PAYPAL_CLIENT_ID', ''), os.getenv('PAYPAL_CLIENT_SECRET', '')))
    port = int(os.getenv('PORT', '8000'))
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'Checkout demo: http://localhost:{port} (Sandbox only)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
