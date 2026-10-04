"""Persistent booking orchestration. Every network call occurs outside transactions."""
import secrets
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from payments import PayPalError
from storage import attempts, bookings, entitlements, identifier, money, workshops

RETENTION_SECONDS = 6 * 3600
LEASE_SECONDS = 120


class CheckoutError(Exception):
    def __init__(self, issue, status=409):
        self.issue, self.status = issue, status


class Checkout:
    def __init__(self, store, paypal):
        self.store, self.paypal = store, paypal

    def _load(self, participant_id, booking_id=None, order_id=None):
        with self.store.engine.connect() as connection:
            query = select(bookings).where(bookings.c.participant_id == participant_id)
            if order_id:
                query = query.join(attempts, bookings.c.active_attempt_id == attempts.c.id).where(attempts.c.order_id == order_id)
            else:
                query = query.where(bookings.c.id == booking_id)
            booking = connection.execute(query).mappings().first()
            if not booking:
                raise CheckoutError('BOOKING_NOT_FOUND', 404)
            workshop = connection.execute(select(workshops).where(workshops.c.id == booking['workshop_id'])).mappings().one()
            attempt = connection.execute(select(attempts).where(attempts.c.id == booking['active_attempt_id'])).mappings().first()
            return dict(booking), dict(workshop), dict(attempt) if attempt else None

    def _attempt(self, booking_id, workshop):
        return dict(id=identifier(), booking_id=booking_id, state='CREATING', create_key=identifier(),
            capture_key=identifier(), order_id=None, capture_id=None, merchant_id=self.paypal.merchant_id,
            price_minor=workshop['price_minor'], currency=workshop['currency'], created_at=time.time(),
            capture_started_at=None, error=None, debug_id=None, lease_token=None, lease_until=0)

    def _ensure_booking(self, participant_id, workshop_id):
        try:
            with self.store.engine.begin() as connection:
                workshop = connection.execute(select(workshops).where(workshops.c.id == workshop_id)).mappings().first()
                if not workshop:
                    raise CheckoutError('WORKSHOP_NOT_FOUND', 404)
                existing = connection.execute(select(bookings).where(bookings.c.participant_id == participant_id,
                    bookings.c.workshop_id == workshop_id)).mappings().first()
                if existing:
                    return existing['id']
                if datetime.fromisoformat(workshop['starts_at']) <= datetime.now(timezone.utc):
                    raise CheckoutError('WORKSHOP_ALREADY_STARTED')
                booking_id = identifier()
                attempt = self._attempt(booking_id, workshop)
                connection.execute(insert(bookings).values(id=booking_id, participant_id=participant_id,
                    workshop_id=workshop_id, state='PAYMENT_IN_PROGRESS', active_attempt_id=attempt['id']))
                connection.execute(insert(attempts).values(**attempt))
                return booking_id
        except IntegrityError:
            # A competing request won the participant/workshop uniqueness constraint.
            with self.store.engine.connect() as connection:
                booking_id = connection.execute(select(bookings.c.id).where(
                    bookings.c.participant_id == participant_id, bookings.c.workshop_id == workshop_id)).scalar()
            if not booking_id:
                raise
            return booking_id

    def view(self, participant_id, booking_id):
        booking, workshop, attempt = self._load(participant_id, booking_id)
        state = attempt['state'] if attempt else 'UNPAID'
        messages = {
            'CREATING': 'Creating your checkout. Recheck if this takes longer than expected.',
            'AWAITING_APPROVAL': 'Approve your own payment in PayPal to book this workshop.',
            'APPROVED': 'Buyer approved. Payment has not yet been confirmed.',
            'CAPTURING': 'Confirming your payment. Please do not pay again.',
            'PENDING': 'PayPal is processing your payment. Access stays locked until completion.',
            'UNKNOWN': 'Payment outcome is uncertain. Recheck payment; do not start another purchase.',
            'COMPLETED': 'Your payment is complete. Your sample lesson is ready.',
            'DENIED': 'PayPal declined this payment. You may start a fresh checkout after rechecking.',
            'CANCELLED': 'Checkout was closed. Payment has not been confirmed; you can resume this order.',
        }
        can_pay = state in ('AWAITING_APPROVAL', 'APPROVED', 'CANCELLED', 'DENIED') and attempt['lease_until'] <= time.time()
        return dict(id=booking['id'], workshopID=workshop['id'], workshopTitle=workshop['title'],
            value=money(attempt['price_minor'] if attempt else workshop['price_minor']), currency=workshop['currency'],
            bookingState=booking['state'], attemptState=state, orderID=attempt['order_id'] if attempt else None,
            captureID=attempt['capture_id'] if attempt else None, canPay=bool(can_pay),
            message=messages.get(state, 'Recheck your booking status.'),
            debugID=attempt['debug_id'] if attempt else None,
            lessonURL=f'/lessons/{booking_id}' if booking['state'] == 'CONFIRMED' else None)

    def list(self, participant_id):
        with self.store.engine.connect() as connection:
            ids = connection.execute(select(bookings.c.id).where(bookings.c.participant_id == participant_id)).scalars().all()
        return [self.view(participant_id, key) for key in ids]

    def _claim(self, attempt_id):
        token = secrets.token_hex(24)
        with self.store.engine.begin() as connection:
            result = connection.execute(update(attempts).where(attempts.c.id == attempt_id,
                attempts.c.lease_until <= time.time()).values(lease_token=token, lease_until=time.time() + LEASE_SECONDS))
        return token if result.rowcount == 1 else None

    def _save(self, attempt_id, token, **values):
        with self.store.engine.begin() as connection:
            result = connection.execute(update(attempts).where(attempts.c.id == attempt_id,
                attempts.c.lease_token == token, attempts.c.lease_until > time.time()).values(**values))
        return result.rowcount == 1

    def _release(self, attempt_id, token):
        self._save(attempt_id, token, lease_token=None, lease_until=0)

    def _reload_attempt(self, attempt_id):
        with self.store.engine.connect() as connection:
            return dict(connection.execute(select(attempts).where(attempts.c.id == attempt_id)).mappings().one())

    def _error(self, attempt, token, error, definite_decline=False):
        state = 'DENIED' if definite_decline else 'UNKNOWN'
        saved = self._save(attempt['id'], token, state=state, error=error.issue, debug_id=error.debug_id)
        if saved and state == 'DENIED':
            with self.store.engine.begin() as connection:
                connection.execute(update(bookings).where(bookings.c.id == attempt['booking_id'],
                    bookings.c.active_attempt_id == attempt['id'], bookings.c.state != 'CONFIRMED').values(state='UNPAID'))

    def _validate_order(self, booking, attempt, order):
        if order.get('id') != attempt['order_id'] or order.get('intent') not in (None, 'CAPTURE'):
            raise PayPalError('ORDER_CORRELATION_MISMATCH')
        units = order.get('purchase_units') or []
        if len(units) != 1:
            raise PayPalError('PURCHASE_UNIT_MISMATCH')
        unit = units[0]
        if unit.get('custom_id') != booking['id'] or unit.get('reference_id') != booking['id']:
            raise PayPalError('BOOKING_CORRELATION_MISMATCH')
        merchant_id = unit.get('payee', {}).get('merchant_id')
        if not isinstance(merchant_id, str) or not merchant_id:
            raise PayPalError('MERCHANT_ID_MISSING')
        if attempt['merchant_id'] and merchant_id != attempt['merchant_id']:
            raise PayPalError('MERCHANT_MISMATCH')
        if unit.get('amount') != {'value': money(attempt['price_minor']), 'currency_code': attempt['currency']}:
            raise PayPalError('ORDER_AMOUNT_MISMATCH')
        return unit

    def _observe(self, booking, attempt, token, order):
        unit = self._validate_order(booking, attempt, order)
        if not attempt['merchant_id']:
            # The order was created without a payee override using this app's
            # OAuth credentials. Persist its authenticated seller before capture.
            merchant_id = unit['payee']['merchant_id']
            if not self._save(attempt['id'], token, merchant_id=merchant_id):
                return
            attempt['merchant_id'] = merchant_id
        captures = unit.get('payments', {}).get('captures', [])
        if len(captures) > 1:
            raise PayPalError('MULTIPLE_CAPTURES_REQUIRE_REVIEW')
        if not captures and attempt['capture_id']:
            detail = self.paypal.get_capture(attempt['capture_id'])
            if detail.get('id') != attempt['capture_id']:
                raise PayPalError('CAPTURE_CORRELATION_MISMATCH')
            if detail.get('supplementary_data', {}).get('related_ids', {}).get('order_id') not in (None, attempt['order_id']):
                raise PayPalError('CAPTURE_CORRELATION_MISMATCH')
            captures = [detail]
        if not captures:
            # Absence of a capture does not resolve an interrupted capture request.
            if attempt['capture_started_at'] or attempt['state'] == 'DENIED':
                return
            state = 'APPROVED' if order.get('status') == 'APPROVED' else 'AWAITING_APPROVAL'
            if attempt['state'] == 'CANCELLED':
                state = 'CANCELLED'
            self._save(attempt['id'], token, state=state, error=None)
            return
        capture = captures[0]
        capture_id = capture.get('id')
        if not capture_id:
            raise PayPalError('CAPTURE_ID_MISSING')
        if attempt['capture_id'] and capture_id != attempt['capture_id']:
            raise PayPalError('CAPTURE_CORRELATION_MISMATCH')
        # Save the discovered identifier before a retryable detail request.
        if not self._save(attempt['id'], token, capture_id=capture_id):
            return
        # GET capture when its detailed state is known to be pending, or absent.
        if capture.get('status') == 'PENDING' or not capture.get('status'):
            detail = self.paypal.get_capture(capture_id)
            if detail.get('id') != capture_id:
                raise PayPalError('CAPTURE_CORRELATION_MISMATCH')
            if detail.get('supplementary_data', {}).get('related_ids', {}).get('order_id') not in (None, attempt['order_id']):
                raise PayPalError('CAPTURE_CORRELATION_MISMATCH')
            capture = detail
        try:
            amount = capture.get('amount', {})
            matches = (amount.get('currency_code') == attempt['currency'] and
                       Decimal(amount.get('value', 'NaN')) == Decimal(money(attempt['price_minor'])))
        except (InvalidOperation, TypeError):
            matches = False
        if not matches:
            raise PayPalError('CAPTURE_AMOUNT_MISMATCH')
        state = {'COMPLETED': 'COMPLETED', 'PENDING': 'PENDING', 'DECLINED': 'DENIED',
                 'DENIED': 'DENIED', 'FAILED': 'DENIED'}.get(capture.get('status'), 'UNKNOWN')
        with self.store.engine.begin() as connection:
            result = connection.execute(update(attempts).where(attempts.c.id == attempt['id'],
                attempts.c.lease_token == token, attempts.c.lease_until > time.time()).values(state=state, capture_id=capture_id, error=None))
            if result.rowcount != 1:
                return
            if state == 'COMPLETED':
                updated = connection.execute(update(bookings).where(bookings.c.id == booking['id'],
                    bookings.c.active_attempt_id == attempt['id']).values(state='CONFIRMED'))
                if updated.rowcount != 1:
                    raise CheckoutError('STALE_PAYMENT_ATTEMPT')
                if not connection.execute(select(entitlements.c.booking_id).where(entitlements.c.booking_id == booking['id'])).first():
                    connection.execute(insert(entitlements).values(booking_id=booking['id'], capture_id=capture_id,
                        granted_at=time.time()))
            elif state == 'DENIED':
                connection.execute(update(bookings).where(bookings.c.id == booking['id'],
                    bookings.c.active_attempt_id == attempt['id'], bookings.c.state != 'CONFIRMED').values(state='UNPAID'))

    def initiate(self, participant_id, workshop_id):
        if not self.paypal.configured:
            raise CheckoutError('SANDBOX_CONFIGURATION_MISSING', 503)
        booking_id = self._ensure_booking(participant_id, workshop_id)
        booking, workshop, attempt = self._load(participant_id, booking_id)
        if booking['state'] == 'CONFIRMED':
            return self.view(participant_id, booking_id)
        # Resolve an existing order before replacement or returning checkout eligibility.
        if attempt['order_id']:
            self.reconcile(participant_id, booking_id)
            booking, workshop, attempt = self._load(participant_id, booking_id)
            if attempt['state'] == 'DENIED':
                replacement_token = self._claim(attempt['id'])
                if not replacement_token:
                    return self.view(participant_id, booking_id)
                try:
                    current = self._reload_attempt(attempt['id'])
                    if current['state'] == 'DENIED':
                        with self.store.engine.begin() as connection:
                            replacement = self._attempt(booking_id, workshop)
                            guarded = select(attempts.c.id).where(attempts.c.id == current['id'],
                                attempts.c.state == 'DENIED', attempts.c.lease_token == replacement_token,
                                attempts.c.lease_until > time.time()).exists()
                            result = connection.execute(update(bookings).where(bookings.c.id == booking_id,
                                bookings.c.state != 'CONFIRMED', bookings.c.active_attempt_id == current['id'],
                                guarded).values(active_attempt_id=replacement['id'], state='PAYMENT_IN_PROGRESS'))
                            if result.rowcount == 1:
                                connection.execute(insert(attempts).values(**replacement))
                finally:
                    self._release(attempt['id'], replacement_token)
                booking, workshop, attempt = self._load(participant_id, booking_id)
            elif attempt['state'] == 'CANCELLED':
                with self.store.engine.begin() as connection:
                    connection.execute(update(attempts).where(attempts.c.id == attempt['id'],
                        attempts.c.state == 'CANCELLED', attempts.c.lease_until <= time.time()).values(state='AWAITING_APPROVAL'))
                return self.view(participant_id, booking_id)
            else:
                return self.view(participant_id, booking_id)
        token = self._claim(attempt['id'])
        if not token:
            return self.view(participant_id, booking_id)
        try:
            attempt = self._reload_attempt(attempt['id'])
            if attempt['order_id']:
                return self.view(participant_id, booking_id)
            if time.time() - attempt['created_at'] >= RETENTION_SECONDS:
                self._save(attempt['id'], token, state='UNKNOWN', error='CREATE_RETRY_WINDOW_EXPIRED')
                return self.view(participant_id, booking_id)
            payload = {'intent': 'CAPTURE', 'purchase_units': [{
                'reference_id': booking_id, 'custom_id': booking_id,
                'description': workshop['title'],
                'amount': {'currency_code': attempt['currency'], 'value': money(attempt['price_minor'])}}],
                'application_context': {'shipping_preference': 'NO_SHIPPING'}}
            order = self.paypal.create_order(payload, attempt['create_key'])
            order_id = order.get('id')
            if not order_id or not isinstance(order_id, str):
                raise PayPalError('ORDER_ID_MISSING')
            if self._save(attempt['id'], token, order_id=order_id, state='AWAITING_APPROVAL', error=None):
                attempt = self._reload_attempt(attempt['id'])
                self._observe(booking, attempt, token, self.paypal.get_order(order_id))
        except PayPalError as error:
            self._error(attempt, token, error)
        finally:
            self._release(attempt['id'], token)
        return self.view(participant_id, booking_id)

    def reconcile(self, participant_id, booking_id):
        booking, workshop, attempt = self._load(participant_id, booking_id)
        if booking['state'] == 'CONFIRMED':
            return self.view(participant_id, booking_id)
        token = self._claim(attempt['id'])
        if not token:
            return self.view(participant_id, booking_id)
        retry_create = False
        retry_capture = False
        try:
            attempt = self._reload_attempt(attempt['id'])
            if not attempt['order_id']:
                self._save(attempt['id'], token, state='UNKNOWN')
                retry_create = time.time() - attempt['created_at'] < RETENTION_SECONDS
            else:
                order = self.paypal.get_order(attempt['order_id'])
                self._observe(booking, attempt, token, order)
                current = self._reload_attempt(attempt['id'])
                retry_capture = (current['state'] in ('UNKNOWN', 'CAPTURING') and
                    current['capture_started_at'] is not None and order.get('status') == 'APPROVED' and
                    time.time() - current['capture_started_at'] < RETENTION_SECONDS)
        except PayPalError as error:
            self._error(attempt, token, error)
        finally:
            self._release(attempt['id'], token)
        if retry_create:
            return self.initiate(participant_id, workshop['id'])
        if retry_capture:
            return self.capture(participant_id, attempt['order_id'])
        return self.view(participant_id, booking_id)

    def capture(self, participant_id, order_id):
        booking, _, attempt = self._load(participant_id, order_id=order_id)
        if booking['state'] == 'CONFIRMED':
            return self.view(participant_id, booking['id'])
        token = self._claim(attempt['id'])
        if not token:
            return self.view(participant_id, booking['id'])
        try:
            attempt = self._reload_attempt(attempt['id'])
            order = self.paypal.get_order(order_id)
            self._observe(booking, attempt, token, order)
            attempt = self._reload_attempt(attempt['id'])
            if attempt['state'] in ('COMPLETED', 'PENDING', 'DENIED'):
                return self.view(participant_id, booking['id'])
            if order.get('status') != 'APPROVED':
                return self.view(participant_id, booking['id'])
            started = attempt['capture_started_at'] or time.time()
            if time.time() - started >= RETENTION_SECONDS:
                self._save(attempt['id'], token, state='UNKNOWN', error='CAPTURE_RETRY_WINDOW_EXPIRED')
                return self.view(participant_id, booking['id'])
            if not self._save(attempt['id'], token, state='CAPTURING', capture_started_at=started):
                return self.view(participant_id, booking['id'])
            try:
                response = self.paypal.capture_order(order_id, attempt['capture_key'])
                if response.get('id') != order_id:
                    raise PayPalError('CAPTURE_ORDER_MISMATCH')
                # Persist known capture ID before additional network verification.
                units = response.get('purchase_units') or []
                captures = units[0].get('payments', {}).get('captures', []) if len(units) == 1 else []
                if len(captures) == 1 and captures[0].get('id'):
                    self._save(attempt['id'], token, capture_id=captures[0]['id'])
            except PayPalError as error:
                self._error(attempt, token, error, definite_decline=(error.issue == 'INSTRUMENT_DECLINED' and not error.uncertain))
            # Authenticated GET order supplies payee and booking correlation even
            # when the capture representation omits them or its response was lost.
            attempt = self._reload_attempt(attempt['id'])
            self._observe(booking, attempt, token, self.paypal.get_order(order_id))
        except PayPalError as error:
            self._error(attempt, token, error)
        finally:
            self._release(attempt['id'], token)
        return self.view(participant_id, booking['id'])

    def cancel(self, participant_id, booking_id):
        booking, _, attempt = self._load(participant_id, booking_id)
        if booking['state'] != 'CONFIRMED':
            with self.store.engine.begin() as connection:
                result = connection.execute(update(attempts).where(attempts.c.id == attempt['id'],
                    attempts.c.state.in_(['AWAITING_APPROVAL', 'APPROVED']),
                    attempts.c.capture_started_at.is_(None), attempts.c.lease_until <= time.time()).values(state='CANCELLED'))
                if result.rowcount == 1:
                    connection.execute(update(bookings).where(bookings.c.id == booking_id,
                        bookings.c.active_attempt_id == attempt['id'], bookings.c.state != 'CONFIRMED').values(state='UNPAID'))
        return self.view(participant_id, booking_id)

    def lesson(self, participant_id, booking_id):
        booking, workshop, _ = self._load(participant_id, booking_id)
        with self.store.engine.connect() as connection:
            granted = connection.execute(select(entitlements).where(entitlements.c.booking_id == booking_id)).first()
        if booking['state'] != 'CONFIRMED' or not granted:
            raise CheckoutError('PAYMENT_NOT_COMPLETED', 403)
        return workshop
