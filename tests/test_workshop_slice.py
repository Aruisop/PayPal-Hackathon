"""Payment-contract tests. Fake PayPal models external state independently of the DB."""
import copy
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy import event
from unittest.mock import patch

from payments import PayPal, PayPalError
from server import create_app
from storage import attempts


class FakePayPal:
    client_id = 'test-client'
    merchant_id = 'MERCHANT123'
    configured = True

    def __init__(self):
        self.orders = {}
        self.create_keys = {}
        self.capture_keys = {}
        self.create_calls = 0
        self.capture_calls = 0
        self.get_calls = 0
        self.capture_get_calls = 0
        self.capture_status = 'COMPLETED'
        self.lose_capture_response = False
        self.reject_capture = False
        self.fail_create = False
        self.fail_capture_without_result = False
        self.hide_order_captures = False
        self.lock = threading.Lock()

    def create_order(self, payload, request_id):
        with self.lock:
            self.create_calls += 1
            if self.fail_create:
                raise PayPalError('PAYPAL_UNAVAILABLE')
            if request_id in self.create_keys:
                return copy.deepcopy(self.orders[self.create_keys[request_id]])
            order_id = f'ORDER{len(self.orders) + 1}'
            order = dict(id=order_id, intent=payload['intent'], status='CREATED',
                         purchase_units=copy.deepcopy(payload['purchase_units']))
            order['purchase_units'][0]['payee'] = {'merchant_id': 'MERCHANT123'}
            self.orders[order_id] = order
            self.create_keys[request_id] = order_id
            return copy.deepcopy(order)

    def approve(self, order_id):
        self.orders[order_id]['status'] = 'APPROVED'

    def capture_order(self, order_id, request_id):
        with self.lock:
            self.capture_calls += 1
            if self.reject_capture:
                raise PayPalError('INSTRUMENT_DECLINED', uncertain=False, provider_status=422)
            if self.fail_capture_without_result:
                raise PayPalError('PAYPAL_UNAVAILABLE')
            order = self.orders[order_id]
            if request_id not in self.capture_keys:
                capture = dict(id=f'CAPTURE{len(self.capture_keys) + 1}', status=self.capture_status,
                               amount=copy.deepcopy(order['purchase_units'][0]['amount']))
                order['purchase_units'][0]['payments'] = {'captures': [capture]}
                order['status'] = 'COMPLETED'
                self.capture_keys[request_id] = capture['id']
            if self.lose_capture_response:
                raise PayPalError('PAYPAL_UNAVAILABLE')
            # Real capture responses can omit merchant/correlation fields.
            return dict(id=order_id, status=order['status'], purchase_units=[{
                'payments': copy.deepcopy(order['purchase_units'][0]['payments'])}])

    def get_order(self, order_id):
        self.get_calls += 1
        result = copy.deepcopy(self.orders[order_id])
        if self.hide_order_captures:
            result['purchase_units'][0].pop('payments', None)
        return result

    def get_capture(self, capture_id):
        self.capture_get_calls += 1
        for order in self.orders.values():
            for capture in order['purchase_units'][0].get('payments', {}).get('captures', []):
                if capture['id'] == capture_id:
                    result = copy.deepcopy(capture)
                    result['supplementary_data'] = {'related_ids': {'order_id': order['id']}}
                    return result
        raise PayPalError('RESOURCE_NOT_FOUND', provider_status=404)


class WorkshopSliceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.fake = FakePayPal()
        self.config = dict(DATABASE_URL='sqlite:///' + (Path(self.directory.name) / 'test.db').as_posix(),
                           APP_ORIGIN='http://localhost', COOKIE_SECURE=False, APP_ENV='development', TESTING=True)
        self.app = create_app(self.config, paypal=self.fake)
        self.buyer = self.app.test_client()
        self.other = self.app.test_client()
        self.buyer_csrf = self.buyer.get('/api/config').json['csrfToken']
        self.other_csrf = self.other.get('/api/config').json['csrfToken']

    def tearDown(self):
        self.app.extensions['store'].engine.dispose()
        self.directory.cleanup()

    def post(self, path, body=None, client=None, csrf=None):
        return (client or self.buyer).post(path, json=body or {}, headers={
            'Origin': 'http://localhost', 'X-CSRF-Token': csrf or self.buyer_csrf})

    def initiate(self, **extra):
        response = self.post('/api/orders', dict(workshopID='interview-basics', **extra))
        self.assertEqual(response.status_code, 200)
        return response.json

    def capture(self, booking):
        self.fake.approve(booking['orderID'])
        return self.post(f'/api/orders/{booking["orderID"]}/capture')

    def mutate_attempt(self, booking, **values):
        store = self.app.extensions['store']
        with store.engine.begin() as connection:
            connection.execute(update(attempts).where(attempts.c.booking_id == booking['id']).values(**values))

    def test_catalog_has_two_scheduled_usd_workshops(self):
        catalog = self.buyer.get('/api/config').json['workshops']
        self.assertEqual(len(catalog), 2)
        self.assertEqual({w['value'] for w in catalog}, {'25.00', '18.00'})
        self.assertTrue(all(w['currency'] == 'USD' and w['startsAt'] < w['endsAt'] for w in catalog))

    def test_browser_amount_currency_and_merchant_are_ignored(self):
        booking = self.initiate(amount='0.01', currency='INR', merchantID='ATTACKER')
        unit = self.fake.orders[booking['orderID']]['purchase_units'][0]
        self.assertEqual(unit['amount'], {'value': '25.00', 'currency_code': 'USD'})
        self.assertEqual(unit['payee']['merchant_id'], self.fake.merchant_id)
        self.assertEqual(unit['custom_id'], booking['id'])

    def test_merchant_setting_optional_and_seller_persisted_before_capture(self):
        self.assertTrue(PayPal('test-client', 'test-secret').configured)
        self.assertFalse(PayPal('test-client', '').configured)
        self.fake.merchant_id = ''
        original_create = self.fake.create_order
        def create_without_override(payload, request_id):
            self.assertNotIn('payee', payload['purchase_units'][0])
            return original_create(payload, request_id)
        with patch.object(self.fake, 'create_order', side_effect=create_without_override):
            booking = self.initiate()
        with self.app.extensions['store'].engine.connect() as connection:
            saved = connection.execute(select(attempts.c.merchant_id).where(
                attempts.c.booking_id == booking['id'])).scalar_one()
        self.assertEqual(saved, 'MERCHANT123')
        # Later seller changes cannot bypass the persisted expectation.
        self.fake.orders[booking['orderID']]['purchase_units'][0]['payee']['merchant_id'] = 'OTHER'
        self.assertEqual(self.capture(booking).json['attemptState'], 'UNKNOWN')
        self.assertEqual(self.fake.capture_calls, 0)
        self.fake.orders[booking['orderID']]['purchase_units'][0]['payee']['merchant_id'] = saved
        self.assertEqual(self.capture(booking).json['bookingState'], 'CONFIRMED')

    def test_duplicate_initiation_and_capture_return_same_purchase(self):
        booking = self.initiate()
        duplicate = self.initiate()
        self.assertEqual(booking['id'], duplicate['id'])
        self.assertEqual(booking['orderID'], duplicate['orderID'])
        self.assertEqual(self.fake.create_calls, 1)
        completed = self.capture(booking).json
        repeated = self.post(f'/api/orders/{booking["orderID"]}/capture').json
        self.assertEqual(completed['captureID'], repeated['captureID'])
        self.assertEqual(self.fake.capture_calls, 1)
        self.assertEqual(self.initiate()['captureID'], completed['captureID'])
        self.assertEqual(self.fake.create_calls, 1)

    def test_approval_alone_does_not_unlock_lesson(self):
        booking = self.initiate()
        self.fake.approve(booking['orderID'])
        observed = self.post(f'/api/bookings/{booking["id"]}/reconcile').json
        self.assertEqual(observed['attemptState'], 'APPROVED')
        self.assertIsNone(observed['lessonURL'])
        self.assertEqual(self.buyer.get(f'/lessons/{booking["id"]}').status_code, 403)

    def test_reload_reconciles_approval_then_owner_completes_saved_order(self):
        booking = self.initiate()
        self.fake.approve(booking['orderID'])
        # The browser reloads before SDK onApprove can call the capture route.
        cookie = self.buyer.get_cookie('workshop_session').value
        with self.app.extensions['store'].engine.connect() as connection:
            attempt = connection.execute(select(attempts).where(
                attempts.c.booking_id == booking['id'])).mappings().one()
            capture_key = attempt['capture_key']
            self.assertEqual(attempt['state'], 'AWAITING_APPROVAL')
            self.assertIsNone(attempt['capture_started_at'])
        self.app.extensions['store'].engine.dispose()
        self.app = create_app(self.config, paypal=self.fake)
        self.buyer = self.app.test_client()
        self.buyer.set_cookie('workshop_session', cookie)
        restored = self.buyer.get('/api/config').json['bookings'][0]
        self.assertEqual(restored['attemptState'], 'AWAITING_APPROVAL')
        self.assertIsNone(restored['lessonURL'])

        # Page restoration reconciles before rendering Complete payment; it must
        # not capture automatically.
        restored = self.post(f'/api/bookings/{booking["id"]}/reconcile').json
        self.assertEqual(restored['attemptState'], 'APPROVED')
        self.assertEqual(restored['orderID'], booking['orderID'])
        self.assertFalse(restored['lessonURL'])
        self.assertEqual(self.fake.capture_calls, 0)
        with self.app.extensions['store'].engine.connect() as connection:
            attempt = connection.execute(select(attempts).where(
                attempts.c.booking_id == booking['id'])).mappings().one()
            self.assertEqual(attempt['capture_key'], capture_key)
            self.assertIsNone(attempt['capture_started_at'])

        # The explicit owner action uses the existing order capture endpoint.
        completed = self.post(f'/api/orders/{booking["orderID"]}/capture').json
        self.assertEqual(completed['attemptState'], 'COMPLETED')
        self.assertEqual(completed['bookingState'], 'CONFIRMED')
        self.assertEqual(completed['lessonURL'], f'/lessons/{booking["id"]}')
        self.assertEqual(self.fake.create_calls, 1)
        self.assertEqual(self.fake.capture_calls, 1)

    def test_concurrent_complete_payment_requests_capture_once(self):
        booking = self.initiate()
        self.fake.approve(booking['orderID'])
        self.post(f'/api/bookings/{booking["id"]}/reconcile')
        cookie = self.buyer.get_cookie('workshop_session').value
        def complete(_):
            with self.app.test_client() as client:
                client.set_cookie('workshop_session', cookie)
                return client.post(f'/api/orders/{booking["orderID"]}/capture', json={}, headers={
                    'Origin': 'http://localhost', 'X-CSRF-Token': self.buyer_csrf}).json
        with ThreadPoolExecutor(max_workers=4) as workers:
            responses = list(workers.map(complete, range(4)))
        self.assertEqual(self.fake.capture_calls, 1)
        participant = self.app.extensions['store'].participant(cookie)
        final = self.app.extensions['checkout'].view(participant['id'], booking['id'])
        self.assertEqual(final['attemptState'], 'COMPLETED')
        self.assertTrue(all(response['id'] == booking['id'] for response in responses))

    def test_other_participant_cannot_complete_approved_booking(self):
        booking = self.initiate()
        self.fake.approve(booking['orderID'])
        self.post(f'/api/bookings/{booking["id"]}/reconcile')
        response = self.post(f'/api/orders/{booking["orderID"]}/capture', client=self.other,
                             csrf=self.other_csrf)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.fake.capture_calls, 0)
        self.assertEqual(self.buyer.get(f'/lessons/{booking["id"]}').status_code, 403)

    def test_owner_complete_action_keeps_pending_capture_locked(self):
        booking = self.initiate()
        self.fake.approve(booking['orderID'])
        approved = self.post(f'/api/bookings/{booking["id"]}/reconcile').json
        self.assertEqual(approved['attemptState'], 'APPROVED')
        self.fake.capture_status = 'PENDING'
        pending = self.post(f'/api/orders/{booking["orderID"]}/capture').json
        self.assertEqual(pending['attemptState'], 'PENDING')
        self.assertIsNone(pending['lessonURL'])
        self.assertEqual(self.buyer.get(f'/lessons/{booking["id"]}').status_code, 403)
        repeated = self.post(f'/api/orders/{booking["orderID"]}/capture').json
        self.assertEqual(repeated['attemptState'], 'PENDING')
        self.assertEqual(self.fake.capture_calls, 1)

    def test_completed_capture_unlocks_only_own_lesson_and_receipt(self):
        booking = self.initiate()
        completed = self.capture(booking).json
        self.assertEqual(completed['bookingState'], 'CONFIRMED')
        self.assertEqual(completed['attemptState'], 'COMPLETED')
        self.assertEqual(self.buyer.get(completed['lessonURL']).status_code, 200)
        for path in (f'/api/bookings/{booking["id"]}', completed['lessonURL']):
            self.assertEqual(self.other.get(path).status_code, 404)
        self.assertEqual(self.other.get('/api/bookings').json['bookings'], [])
        response = self.post(f'/api/orders/{booking["orderID"]}/capture',
                             client=self.other, csrf=self.other_csrf)
        self.assertEqual(response.status_code, 404)
        for suffix in ('reconcile', 'cancel'):
            response = self.post(f'/api/bookings/{booking["id"]}/{suffix}',
                                 client=self.other, csrf=self.other_csrf)
            self.assertEqual(response.status_code, 404)

    def test_pending_capture_is_locked_then_reconciles_completed(self):
        self.fake.capture_status = 'PENDING'
        booking = self.initiate()
        result = self.capture(booking).json
        self.assertEqual(result['attemptState'], 'PENDING')
        self.assertEqual(self.buyer.get(f'/lessons/{booking["id"]}').status_code, 403)
        self.post(f'/api/orders/{booking["orderID"]}/capture')
        self.assertEqual(self.fake.capture_calls, 1)
        self.fake.orders[booking['orderID']]['purchase_units'][0]['payments']['captures'][0]['status'] = 'COMPLETED'
        result = self.post(f'/api/bookings/{booking["id"]}/reconcile').json
        self.assertEqual(result['bookingState'], 'CONFIRMED')

    def test_lost_capture_response_is_resolved_by_order_get(self):
        self.fake.lose_capture_response = True
        booking = self.initiate()
        result = self.capture(booking).json
        self.assertEqual(result['bookingState'], 'CONFIRMED')
        self.assertEqual(self.fake.capture_calls, 1)
        self.assertGreaterEqual(self.fake.get_calls, 2)

    def test_known_capture_id_is_reconciled_when_order_omits_captures(self):
        self.fake.hide_order_captures = True
        booking = self.initiate()
        result = self.capture(booking).json
        self.assertEqual(result['bookingState'], 'CONFIRMED')
        self.assertGreaterEqual(self.fake.capture_get_calls, 1)

    def test_restart_preserves_cookie_booking_capture_and_access(self):
        booking = self.initiate()
        completed = self.capture(booking).json
        cookie = self.buyer.get_cookie('workshop_session').value
        self.app.extensions['store'].engine.dispose()
        self.app = create_app(self.config, paypal=self.fake)
        restarted = self.app.test_client()
        restarted.set_cookie('workshop_session', cookie)
        config = restarted.get('/api/config').json
        self.assertEqual(config['csrfToken'], self.buyer_csrf)
        self.assertEqual(config['bookings'][0]['captureID'], completed['captureID'])
        self.assertEqual(restarted.get(completed['lessonURL']).status_code, 200)

    def test_discovered_capture_id_survives_detail_request_failure(self):
        booking = self.initiate()
        self.fake.capture_status = 'PENDING'
        self.fake.approve(booking['orderID'])
        self.fake.capture_order(booking['orderID'], 'external-capture')
        capture_id = self.fake.capture_keys['external-capture']
        def fail_detail(identifier):
            with self.app.extensions['store'].engine.connect() as connection:
                saved = connection.execute(select(attempts.c.capture_id).where(
                    attempts.c.booking_id == booking['id'])).scalar_one()
            self.assertEqual(saved, identifier)
            raise PayPalError('PAYPAL_UNAVAILABLE')
        with patch.object(self.fake, 'get_capture', side_effect=fail_detail):
            result = self.post(f'/api/bookings/{booking["id"]}/reconcile').json
        self.assertEqual(result['captureID'], capture_id)
        self.assertEqual(result['attemptState'], 'UNKNOWN')
        self.assertEqual(self.buyer.get(f'/lessons/{booking["id"]}').status_code, 403)
        self.fake.hide_order_captures = True
        self.fake.orders[booking['orderID']]['purchase_units'][0]['payments']['captures'][0]['status'] = 'COMPLETED'
        result = self.post(f'/api/bookings/{booking["id"]}/reconcile').json
        self.assertEqual(result['bookingState'], 'CONFIRMED')
        self.assertEqual(self.fake.capture_calls, 1)

    def test_order_amount_merchant_and_booking_mismatch_never_capture(self):
        booking = self.initiate()
        self.fake.approve(booking['orderID'])
        original = copy.deepcopy(self.fake.orders[booking['orderID']])
        for field, value in [('amount', {'value': '0.01', 'currency_code': 'USD'}),
                             ('payee', {'merchant_id': 'OTHER'}), ('custom_id', 'OTHERBOOKING')]:
            with self.subTest(field=field):
                self.fake.orders[booking['orderID']] = copy.deepcopy(original)
                self.fake.orders[booking['orderID']]['purchase_units'][0][field] = value
                result = self.post(f'/api/orders/{booking["orderID"]}/capture').json
                self.assertEqual(result['attemptState'], 'UNKNOWN')
                self.assertEqual(self.buyer.get(f'/lessons/{booking["id"]}').status_code, 403)
                self.assertEqual(self.fake.capture_calls, 0)

    def test_capture_amount_mismatch_does_not_unlock(self):
        booking = self.initiate()
        self.capture(booking)
        # A second workshop cannot inherit the first booking's entitlement.
        second = self.post('/api/orders', {'workshopID': 'web-basics'}).json
        self.fake.approve(second['orderID'])
        self.fake.capture_order(second['orderID'], 'external-test-capture')
        self.fake.orders[second['orderID']]['purchase_units'][0]['payments']['captures'][0]['amount']['value'] = '0.01'
        result = self.post(f'/api/bookings/{second["id"]}/reconcile').json
        self.assertEqual(result['attemptState'], 'UNKNOWN')
        self.assertEqual(self.buyer.get(f'/lessons/{second["id"]}').status_code, 403)

    def test_unknown_capture_beyond_retention_never_replays_or_replaces(self):
        self.fake.fail_capture_without_result = True
        booking = self.initiate()
        self.assertEqual(self.capture(booking).json['attemptState'], 'UNKNOWN')
        self.mutate_attempt(booking, capture_started_at=time.time() - 6 * 3600 - 1)
        calls = self.fake.capture_calls
        result = self.post(f'/api/orders/{booking["orderID"]}/capture').json
        self.assertEqual(result['attemptState'], 'UNKNOWN')
        self.assertFalse(result['canPay'])
        self.assertEqual(self.fake.capture_calls, calls)
        self.assertEqual(self.initiate()['orderID'], booking['orderID'])
        self.assertEqual(self.fake.create_calls, 1)

    def test_unknown_creation_beyond_retention_is_not_replayed(self):
        self.fake.fail_create = True
        booking = self.initiate()
        self.mutate_attempt(booking, created_at=time.time() - 6 * 3600 - 1)
        self.fake.fail_create = False
        self.assertEqual(self.initiate()['attemptState'], 'UNKNOWN')
        self.assertEqual(self.fake.create_calls, 1)
        self.assertEqual(len(self.fake.orders), 0)

    def test_expired_unapproved_order_missing_at_provider_stays_locked(self):
        booking = self.initiate()
        self.assertEqual(self.fake.orders[booking['orderID']]['status'], 'CREATED')
        self.mutate_attempt(booking, created_at=time.time() - 10 * 86400)
        store = self.app.extensions['store']
        with store.engine.connect() as connection:
            original = dict(connection.execute(select(attempts).where(
                attempts.c.booking_id == booking['id'])).mappings().one())
        # A missing provider resource after expiry does not prove a safe failure.
        with patch.object(self.fake, 'get_order', side_effect=PayPalError(
                'RESOURCE_NOT_FOUND', provider_status=404, uncertain=True)):
            results = [
                self.post(f'/api/bookings/{booking["id"]}/reconcile').json,
                self.initiate(),
                self.post(f'/api/orders/{booking["orderID"]}/capture').json,
            ]
        for result in results:
            self.assertEqual(result['id'], booking['id'])
            self.assertEqual(result['orderID'], booking['orderID'])
            self.assertEqual(result['attemptState'], 'UNKNOWN')
            self.assertNotEqual(result['bookingState'], 'CONFIRMED')
            self.assertFalse(result['canPay'])
            self.assertIsNone(result['lessonURL'])
        self.assertEqual(self.buyer.get(f'/lessons/{booking["id"]}').status_code, 403)
        self.assertEqual(self.fake.create_calls, 1)
        self.assertEqual(self.fake.capture_calls, 0)
        with store.engine.connect() as connection:
            saved = connection.execute(select(attempts).where(
                attempts.c.booking_id == booking['id'])).mappings().all()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]['id'], original['id'])
        self.assertEqual(saved[0]['create_key'], original['create_key'])
        self.assertEqual(saved[0]['capture_key'], original['capture_key'])
        self.assertIsNone(saved[0]['capture_started_at'])

    def test_cancel_resume_uses_same_order_and_decline_stays_locked(self):
        booking = self.initiate()
        cancelled = self.post(f'/api/bookings/{booking["id"]}/cancel').json
        self.assertEqual(cancelled['attemptState'], 'CANCELLED')
        self.assertEqual(self.initiate()['orderID'], booking['orderID'])
        self.fake.reject_capture = True
        result = self.capture(booking).json
        self.assertEqual(result['attemptState'], 'DENIED')
        self.assertEqual(self.buyer.get(f'/lessons/{booking["id"]}').status_code, 403)
        replacement = self.initiate()
        self.assertNotEqual(replacement['orderID'], booking['orderID'])
        self.assertEqual(replacement['id'], booking['id'])

    def test_missing_session_origin_and_csrf_are_rejected(self):
        self.assertEqual(self.app.test_client().get('/api/bookings').status_code, 401)
        self.assertEqual(self.buyer.post('/api/orders', json={'workshopID': 'web-basics'}).status_code, 403)
        response = self.buyer.post('/api/orders', json={'workshopID': 'web-basics'}, headers={
            'Origin': 'http://attacker.example', 'X-CSRF-Token': self.buyer_csrf})
        self.assertEqual(response.status_code, 403)

    def test_concurrent_initiation_and_capture_share_single_attempt(self):
        store = self.app.extensions['store']
        participant, _ = store.new_participant()
        checkout = self.app.extensions['checkout']
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(lambda _: checkout.initiate(participant['id'], 'web-basics'), range(4)))
        booking_ids = {r['id'] for r in results}
        self.assertEqual(len(booking_ids), 1)
        latest = checkout.view(participant['id'], next(iter(booking_ids)))
        self.assertEqual(self.fake.create_calls, 1)
        self.fake.approve(latest['orderID'])
        with ThreadPoolExecutor(max_workers=4) as workers:
            list(workers.map(lambda _: checkout.capture(participant['id'], latest['orderID']), range(4)))
        self.assertEqual(self.fake.capture_calls, 1)
        self.assertEqual(checkout.view(participant['id'], latest['id'])['bookingState'], 'CONFIRMED')
        with store.engine.connect() as connection:
            self.assertEqual(len(connection.execute(select(attempts)).all()), 1)

    def test_unknown_create_recheck_reuses_persisted_key(self):
        self.fake.fail_create = True
        booking = self.initiate()
        store = self.app.extensions['store']
        with store.engine.connect() as connection:
            key = connection.execute(select(attempts.c.create_key).where(attempts.c.booking_id == booking['id'])).scalar_one()
        self.fake.fail_create = False
        result = self.post(f'/api/bookings/{booking["id"]}/reconcile').json
        self.assertEqual(result['attemptState'], 'AWAITING_APPROVAL')
        self.assertIn(key, self.fake.create_keys)
        self.assertEqual(result['id'], booking['id'])

    def test_unknown_capture_recheck_queries_before_same_key_retry(self):
        self.fake.fail_capture_without_result = True
        booking = self.initiate()
        self.capture(booking)
        store = self.app.extensions['store']
        with store.engine.connect() as connection:
            key = connection.execute(select(attempts.c.capture_key).where(attempts.c.booking_id == booking['id'])).scalar_one()
        self.fake.fail_capture_without_result = False
        gets_before = self.fake.get_calls
        result = self.post(f'/api/bookings/{booking["id"]}/reconcile').json
        self.assertEqual(result['bookingState'], 'CONFIRMED')
        self.assertGreater(self.fake.get_calls, gets_before)
        self.assertIn(key, self.fake.capture_keys)
        self.assertEqual(self.fake.create_calls, 1)

    def test_cancel_cannot_erase_pending_payment(self):
        self.fake.capture_status = 'PENDING'
        booking = self.initiate()
        self.capture(booking)
        result = self.post(f'/api/bookings/{booking["id"]}/cancel').json
        self.assertEqual(result['attemptState'], 'PENDING')
        self.assertFalse(result['canPay'])

    def test_expired_lease_worker_does_not_post_capture(self):
        booking = self.initiate()
        self.fake.approve(booking['orderID'])
        real_get = self.fake.get_order
        def expire_during_get(order_id):
            self.mutate_attempt(booking, lease_until=time.time() - 1)
            return real_get(order_id)
        with patch.object(self.fake, 'get_order', side_effect=expire_during_get):
            self.post(f'/api/orders/{booking["orderID"]}/capture')
        self.assertEqual(self.fake.capture_calls, 0)

    def test_completed_booking_is_not_replaced_after_provider_retention(self):
        booking = self.initiate()
        completed = self.capture(booking).json
        self.mutate_attempt(booking, created_at=time.time() - 10 * 86400,
                            capture_started_at=time.time() - 10 * 86400)
        result = self.initiate()
        self.assertEqual(result['captureID'], completed['captureID'])
        self.assertEqual(self.fake.create_calls, 1)
        self.assertEqual(self.fake.capture_calls, 1)

    def test_paypal_calls_are_outside_database_transactions(self):
        engine = self.app.extensions['store'].engine
        active = set()
        def begin(connection): active.add(id(connection))
        def finish(connection): active.discard(id(connection))
        event.listen(engine, 'begin', begin)
        event.listen(engine, 'commit', finish)
        event.listen(engine, 'rollback', finish)
        try:
            original_create = self.fake.create_order
            original_capture = self.fake.capture_order
            original_get = self.fake.get_order
            def outside(function):
                def call(*args):
                    self.assertEqual(active, set(), 'PayPal called inside a DB transaction')
                    return function(*args)
                return call
            with patch.object(self.fake, 'create_order', side_effect=outside(original_create)), \
                 patch.object(self.fake, 'capture_order', side_effect=outside(original_capture)), \
                 patch.object(self.fake, 'get_order', side_effect=outside(original_get)):
                booking = self.initiate()
                self.assertEqual(self.capture(booking).json['bookingState'], 'CONFIRMED')
        finally:
            event.remove(engine, 'begin', begin)
            event.remove(engine, 'commit', finish)
            event.remove(engine, 'rollback', finish)

    def test_production_refuses_ephemeral_sqlite(self):
        with self.assertRaisesRegex(RuntimeError, 'managed PostgreSQL'):
            create_app(dict(self.config, APP_ENV='production', APP_ORIGIN='https://example.com', COOKIE_SECURE=True), self.fake)


if __name__ == '__main__':
    unittest.main()
