"""Small server-only PayPal Sandbox adapter; persistence belongs to booking service."""
import base64
import http.client
import json
import re
import threading
import time
import urllib.error
import urllib.request

BASE = 'https://api-m.sandbox.paypal.com'


class PayPalError(Exception):
    """An API failure is not proof that an attempted capture did not happen."""

    def __init__(self, issue, debug_id='', status=502, uncertain=True,
                 provider_status=None):
        super().__init__(issue)
        self.issue = issue
        self.debug_id = debug_id
        self.status = status
        self.uncertain = uncertain
        self.provider_status = provider_status


class PayPal:
    def __init__(self, client_id, secret, merchant_id=''):
        self.client_id = client_id
        self.secret = secret
        self.merchant_id = merchant_id
        self.token = ''
        self.expires = 0
        self._token_lock = threading.Lock()

    @property
    def configured(self):
        return bool(self.client_id and self.secret)

    def _request(self, method, path, payload=None, headers=None, form=None):
        body = None
        if form is not None:
            body = form.encode('ascii')
        elif method == 'POST':
            body = json.dumps(payload if payload is not None else {}).encode('utf-8')
        request = urllib.request.Request(BASE + path, data=body,
                                         headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.load(response)
            if not isinstance(data, dict):
                raise ValueError('Expected an object')
            return data
        except urllib.error.HTTPError as error:
            try:
                data = json.loads(error.read())
                if not isinstance(data, dict):
                    data = {}
            except (ValueError, UnicodeDecodeError):
                data = {}
            details = data.get('details')
            detail = details[0] if isinstance(details, list) and details else {}
            detail = detail if isinstance(detail, dict) else {}
            issue = detail.get('issue') or data.get('error') or data.get('name') or 'PAYPAL_ERROR'
            # Even a conflict/4xx can describe an earlier successful operation.
            # The caller reconciles against the order before allowing new payment.
            uncertain = issue != 'INSTRUMENT_DECLINED' or error.code >= 500 or error.code == 429
            raise PayPalError(str(issue), str(data.get('debug_id', '')),
                              status=422 if error.code == 422 else 502,
                              uncertain=uncertain, provider_status=error.code) from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError,
                UnicodeDecodeError, http.client.HTTPException):
            raise PayPalError('PAYPAL_UNAVAILABLE', uncertain=True) from None

    def access_token(self):
        # Synchronize only token caching, never a database transaction.
        with self._token_lock:
            if time.monotonic() >= self.expires:
                basic = base64.b64encode(f'{self.client_id}:{self.secret}'.encode()).decode()
                data = self._request('POST', '/v1/oauth2/token', headers={
                    'Authorization': 'Basic ' + basic,
                    'Content-Type': 'application/x-www-form-urlencoded',
                }, form='grant_type=client_credentials')
                try:
                    token = data['access_token']
                    lifetime = int(data['expires_in'])
                    if not isinstance(token, str) or not token or lifetime <= 0:
                        raise ValueError()
                except (KeyError, TypeError, ValueError):
                    raise PayPalError('INVALID_TOKEN_RESPONSE') from None
                self.token = token
                self.expires = time.monotonic() + max(0, lifetime - 60)
            return self.token

    def _authorized(self, method, path, payload=None, request_id=None):
        if not self.configured:
            raise PayPalError('CREDENTIALS_MISSING', status=503, uncertain=False)
        headers = {'Authorization': 'Bearer ' + self.access_token(),
                   'Content-Type': 'application/json', 'Accept': 'application/json'}
        if method == 'POST':
            if not request_id:
                raise ValueError('A persisted request ID is required')
            headers['PayPal-Request-Id'] = request_id
            headers['Prefer'] = 'return=representation'
        return self._request(method, path, payload=payload, headers=headers)

    @staticmethod
    def _identifier(identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9]{1,36}', identifier):
            raise PayPalError('INVALID_PAYPAL_IDENTIFIER', status=400, uncertain=False)
        return identifier

    def create_order(self, payload, request_id):
        return self._authorized('POST', '/v2/checkout/orders', payload, request_id)

    def capture_order(self, order_id, request_id):
        return self._authorized('POST',
                                f'/v2/checkout/orders/{self._identifier(order_id)}/capture',
                                {}, request_id)

    def get_order(self, order_id):
        return self._authorized('GET', f'/v2/checkout/orders/{self._identifier(order_id)}')

    def get_capture(self, capture_id):
        return self._authorized('GET', f'/v2/payments/captures/{self._identifier(capture_id)}')
