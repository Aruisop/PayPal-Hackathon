"""Local-only receipt reading through an on-device Ollama vision model.

This never calls a hosted API, never spends network budget inside a database
transaction, and never confirms a split on anyone's behalf: it only returns
an editable preview. If the local model or Ollama itself is unavailable, the
caller must fall back to manual entry; nothing about the receipt is invented.
"""
import base64
import json
import os
import re
import urllib.error
import urllib.request


class ReceiptScanError(Exception):
    def __init__(self, issue, status=502):
        self.issue, self.status = issue, status
        super().__init__(issue)


CATEGORIES = ('food', 'travel', 'rent', 'entertainment', 'shopping', 'other')
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_CONTENT_TYPES = ('image/jpeg', 'image/png', 'image/webp')
PROMPT = (
    'You are reading a photo of a purchase receipt. Reply with strict JSON only, no prose, '
    'matching exactly this shape: {"merchant": string or null, "date": "YYYY-MM-DD" or null, '
    '"currency": 3-letter code or null, "total": number or null, '
    '"category": one of ["food","travel","rent","entertainment","shopping","other"], '
    '"items": [{"name": string, "amount": number}]}. '
    'Use null for anything you cannot actually read. Never invent an amount you cannot see.'
)


class ReceiptScanner:
    """Thin client for a locally running Ollama server with a vision model pulled."""

    def __init__(self, host=None, model=None, timeout=60):
        self.host = (host or os.getenv('OLLAMA_HOST', 'http://127.0.0.1:11434')).rstrip('/')
        self.model = model or os.getenv('OLLAMA_VISION_MODEL', 'llava:7b')
        self.timeout = timeout

    def status(self):
        """Read-only probe; never used to gate a scan request's own error handling."""
        try:
            request = urllib.request.Request(self.host + '/api/tags', method='GET')
            with urllib.request.urlopen(request, timeout=3) as response:
                tags = json.loads(response.read(200_000))
            names = [m.get('name') for m in tags.get('models', [])]
            return {'available': True, 'model': self.model, 'modelPulled': self.model in names}
        except Exception:
            return {'available': False, 'model': self.model, 'modelPulled': False}

    def scan(self, image_bytes, content_type):
        if not image_bytes:
            raise ReceiptScanError('RECEIPT_IMAGE_REQUIRED', 400)
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise ReceiptScanError('RECEIPT_IMAGE_TOO_LARGE', 400)
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ReceiptScanError('UNSUPPORTED_IMAGE_TYPE', 400)
        encoded = base64.b64encode(image_bytes).decode('ascii')
        payload = json.dumps({
            'model': self.model, 'prompt': PROMPT, 'images': [encoded],
            'stream': False, 'format': 'json', 'options': {'temperature': 0},
        }).encode()
        request = urllib.request.Request(self.host + '/api/generate', data=payload, method='POST',
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read(2_000_000))
        except urllib.error.URLError:
            raise ReceiptScanError('LOCAL_MODEL_UNAVAILABLE', 503)
        except TimeoutError:
            raise ReceiptScanError('LOCAL_MODEL_TIMEOUT', 504)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ReceiptScanError('LOCAL_MODEL_INVALID_RESPONSE', 502)
        raw_text = str(body.get('response', ''))[:4000]
        parsed = self._extract_json(raw_text)
        if not isinstance(parsed, dict):
            return {'parsed': False, 'rawText': raw_text, 'fields': None}
        return {'parsed': True, 'rawText': raw_text, 'fields': self._normalize(parsed)}

    @staticmethod
    def _extract_json(raw_text):
        try:
            return json.loads(raw_text)
        except (ValueError, TypeError):
            match = re.search(r'\{.*\}', raw_text, re.S)
            if not match:
                return None
            try:
                return json.loads(match.group())
            except ValueError:
                return None

    @staticmethod
    def _amount(value):
        try:
            amount = round(float(value), 2)
        except (TypeError, ValueError):
            return None
        return amount if 0 <= amount < 1_000_000 else None

    def _normalize(self, parsed):
        category = parsed.get('category')
        category = category if category in CATEGORIES else 'other'
        items = []
        raw_items = parsed.get('items')
        if isinstance(raw_items, list):
            for item in raw_items[:50]:
                if not isinstance(item, dict):
                    continue
                name, amount = item.get('name'), self._amount(item.get('amount'))
                if isinstance(name, str) and name.strip() and amount is not None:
                    items.append({'name': name.strip()[:160], 'amount': amount})
        date_value = parsed.get('date')
        if not (isinstance(date_value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', date_value)):
            date_value = None
        currency = parsed.get('currency')
        currency = currency.upper() if isinstance(currency, str) and re.fullmatch(r'[A-Za-z]{3}', currency) else None
        merchant = parsed.get('merchant')
        merchant = merchant.strip()[:160] if isinstance(merchant, str) and merchant.strip() else None
        return {
            'merchant': merchant, 'date': date_value, 'currency': currency,
            'total': self._amount(parsed.get('total')), 'category': category, 'items': items,
        }
