"""Durable, fenced coordination of separate Sandbox buyer payments.

GET routes never call this service. Unknown mutating outcomes are reconciled;
financial operations are not blindly repeated when their response is lost.
"""
import re
import time

from sqlalchemy import insert, select, update

from booking_errors import BookingError
from booking_lease import claim_booking
from payment_evidence import (require, validate_amount, validate_authorization,
                              validate_capture, validate_order, validate_refund)
from payments import PayPalError
from storage import (catalog_offers, catalog_resources, group_operations,
                     group_tickets, group_workflows, identifier, money,
                     purchase_contributions, shared_purchases)

CREATE_REPLAY_SECONDS = 6 * 3600
TERMINAL = ('CONFIRMED', 'CANCELLED', 'EXPIRED')


def provider_id(value):
    require(isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9]{1,36}', value)),
            'INVALID_PROVIDER_IDENTIFIER')
    return value


class GroupPayments:
    def __init__(self, booking, paypal):
        self.booking, self.store, self.paypal = booking, booking.store, paypal

    def purchase_for(self, participant_id, group_id, organizer=False):
        from collab_booking import latest_purchase, member_group
        with self.store.engine.connect() as connection:
            member_group(connection, participant_id, group_id, organizer)
            purchase = latest_purchase(connection, group_id)
            if not purchase:
                raise BookingError('NO_ACTIVE_BOOKING', 400)
            return purchase

    def _records(self, purchase_id):
        with self.store.engine.connect() as connection:
            purchase = dict(connection.execute(select(shared_purchases).where(shared_purchases.c.id == purchase_id)).mappings().one())
            workflow = dict(connection.execute(select(group_workflows).where(group_workflows.c.purchase_id == purchase_id)).mappings().one())
            contributions = [dict(row) for row in connection.execute(select(purchase_contributions).where(
                purchase_contributions.c.purchase_id == purchase_id).order_by(
                purchase_contributions.c.created_at, purchase_contributions.c.id)).mappings()]
        return purchase, workflow, contributions

    def _contribution(self, purchase_id, participant_id):
        return next(c for c in self._records(purchase_id)[2] if c['participant_id'] == participant_id)

    def _operation(self, contribution, kind):
        with self.store.engine.connect() as connection:
            row = connection.execute(select(group_operations).where(
                group_operations.c.contribution_id == contribution['id'], group_operations.c.kind == kind)).mappings().first()
        return dict(row) if row else None

    def _prepare(self, lease, contribution, kind, target=None):
        operation = self._operation(contribution, kind)
        if operation:
            return operation
        now = time.time()
        operation = dict(id=identifier(), purchase_id=lease.purchase_id, contribution_id=contribution['id'],
            kind=kind, request_id=identifier(), target_id=target, provider_id=None, state='PREPARED',
            error=None, started_at=now, updated_at=now)
        with lease.write() as connection:
            connection.execute(insert(group_operations).values(**operation))
        return operation

    def _save_operation(self, lease, operation, **values):
        with lease.write() as connection:
            connection.execute(update(group_operations).where(group_operations.c.id == operation['id']).values(
                updated_at=time.time(), **values))
        operation.update(values)

    def _save_contribution(self, lease, contribution, **values):
        with lease.write() as connection:
            connection.execute(update(purchase_contributions).where(purchase_contributions.c.id == contribution['id']).values(**values))
        contribution.update(values)

    def _state(self, lease, state, error=None, **workflow):
        with lease.write() as connection:
            connection.execute(update(shared_purchases).where(shared_purchases.c.id == lease.purchase_id).values(state=state))
            connection.execute(update(group_workflows).where(group_workflows.c.purchase_id == lease.purchase_id).values(
                error=error, updated_at=time.time(), **workflow))

    def _network(self, lease, operation, call):
        # Persist intent before dispatch. A successor sees STARTED and reconciles.
        lease.renew()
        self._save_operation(lease, operation, state='STARTED', error=None)
        try:
            result = call()
            require(isinstance(result, dict), 'INVALID_PROVIDER_RESPONSE')
            return result
        except (PayPalError, KeyError, ValueError, TypeError) as error:
            issue = error.issue if isinstance(error, PayPalError) else 'INVALID_PROVIDER_RESPONSE'
            definite = isinstance(error, PayPalError) and not error.uncertain
            self._save_operation(lease, operation, state='FAILED' if definite else 'UNKNOWN', error=issue)
            self._state(lease, 'RECOVERY_REQUIRED', issue)
            raise BookingError('PAYMENT_RECOVERY_REQUIRED', 502) from None

    def _observe(self, lease, purchase, contribution):
        """Read authenticated resources, saving discovered IDs before further I/O."""
        for kind, field in (('CREATE', 'order_id'), ('AUTHORIZE', 'authorization_id'), ('CAPTURE', 'capture_id')):
            operation = self._operation(contribution, kind)
            if operation and operation['provider_id'] and not contribution[field]:
                self._save_contribution(lease, contribution, **{field: provider_id(operation['provider_id'])})
        if not contribution['order_id']:
            return contribution
        lease.renew()
        order = self.paypal.get_order(contribution['order_id'])
        workflow = self._records(purchase['id'])[1]
        unit, merchant = validate_order(order, contribution, purchase, workflow['merchant_id'])
        if not workflow['merchant_id']:
            with lease.write() as connection:
                connection.execute(update(group_workflows).where(group_workflows.c.purchase_id == purchase['id']).values(merchant_id=merchant))
        authorizations = unit.get('payments', {}).get('authorizations', [])
        require(isinstance(authorizations, list) and len(authorizations) <= 1, 'MULTIPLE_AUTHORIZATIONS_REQUIRE_REVIEW')
        if authorizations:
            auth_id = provider_id(authorizations[0].get('id'))
            require(not contribution['authorization_id'] or contribution['authorization_id'] == auth_id, 'AUTHORIZATION_CORRELATION_MISMATCH')
            self._save_contribution(lease, contribution, authorization_id=auth_id)
            auth_operation = self._operation(contribution, 'AUTHORIZE')
            if auth_operation:
                self._save_operation(lease, auth_operation, provider_id=auth_id)
        captures = unit.get('payments', {}).get('captures', [])
        require(isinstance(captures, list) and len(captures) <= 1, 'MULTIPLE_CAPTURES_REQUIRE_REVIEW')
        if captures:
            cap_id = provider_id(captures[0].get('id'))
            require(not contribution['capture_id'] or contribution['capture_id'] == cap_id, 'CAPTURE_CORRELATION_MISMATCH')
            self._save_contribution(lease, contribution, capture_id=cap_id)
        auth = None
        if contribution['authorization_id']:
            lease.renew()
            auth = self.paypal.get_authorization(contribution['authorization_id'])
            validate_authorization(auth, contribution, purchase, listed_in_order=bool(authorizations))
            auth_state = auth.get('status')
            auth_operation = self._operation(contribution, 'AUTHORIZE')
            if auth_operation and auth_state in ('CREATED', 'CAPTURED', 'PARTIALLY_CAPTURED', 'VOIDED'):
                self._save_operation(lease, auth_operation, state='COMPLETED', provider_id=contribution['authorization_id'])
            capture_operation = self._operation(contribution, 'CAPTURE')
            if not contribution['capture_id']:
                if capture_operation and capture_operation['state'] in ('STARTED', 'UNKNOWN', 'PENDING'):
                    self._save_contribution(lease, contribution, state='CAPTURE_UNKNOWN')
                elif auth_state == 'CREATED':
                    self._save_contribution(lease, contribution, state='AUTHORIZED')
                elif auth_state == 'VOIDED':
                    self._save_contribution(lease, contribution, state='VOIDED')
                else:
                    self._save_contribution(lease, contribution, state='AUTHORIZATION_UNKNOWN')
        if contribution['capture_id']:
            lease.renew()
            capture = self.paypal.get_capture(contribution['capture_id'])
            validate_capture(capture, contribution, purchase, listed_in_order=bool(captures))
            status = capture.get('status')
            state = {'COMPLETED': 'CAPTURED', 'PENDING': 'CAPTURE_PENDING', 'DECLINED': 'CAPTURE_FAILED',
                     'DENIED': 'CAPTURE_FAILED', 'FAILED': 'CAPTURE_FAILED', 'REFUNDED': 'REFUNDED'}.get(status, 'CAPTURE_UNKNOWN')
            self._save_contribution(lease, contribution, state=state)
            operation = self._operation(contribution, 'CAPTURE')
            if operation:
                operation_state = {'CAPTURED': 'COMPLETED', 'REFUNDED': 'COMPLETED',
                                   'CAPTURE_PENDING': 'PENDING', 'CAPTURE_FAILED': 'FAILED'}.get(state, 'UNKNOWN')
                self._save_operation(lease, operation, state=operation_state, provider_id=contribution['capture_id'])
        elif not contribution['authorization_id']:
            auth_operation = self._operation(contribution, 'AUTHORIZE')
            state = 'AUTHORIZATION_UNKNOWN' if auth_operation and auth_operation['state'] != 'PREPARED' else 'AWAITING_APPROVAL'
            self._save_contribution(lease, contribution, state=state)
        contribution['providerOrderStatus'] = order.get('status')
        return contribution

    def _checked_observe(self, lease, purchase, contribution):
        try:
            return self._observe(lease, purchase, contribution)
        except (PayPalError, KeyError, TypeError, ValueError) as error:
            issue = error.issue if isinstance(error, PayPalError) else 'INVALID_PROVIDER_RESPONSE'
            self._state(lease, 'RECOVERY_REQUIRED', issue)
            raise BookingError('PAYMENT_RECOVERY_REQUIRED', 502) from None

    def _check_open(self, purchase, workflow):
        if purchase['state'] in TERMINAL or workflow['cancel_requested']:
            raise BookingError('BOOKING_NOT_ACCEPTING_PAYMENTS')
        if purchase['hold_deadline'] <= time.time():
            raise BookingError('HOLD_DEADLINE_EXPIRED')
        if not self.paypal or not self.paypal.configured:
            raise BookingError('PAYPAL_NOT_CONFIGURED', 503)

    def initiate(self, participant_id, group_id):
        purchase = self.purchase_for(participant_id, group_id)
        with claim_booking(self.store, purchase['id']) as lease:
            purchase, workflow, _ = self._records(purchase['id'])
            self._check_open(purchase, workflow)
            contribution = self._contribution(purchase['id'], participant_id)
            if not contribution['consent_given_at']:
                raise BookingError('CONSENT_REQUIRED', 400)
            if contribution['authorization_id']:
                raise BookingError('SHARE_ALREADY_AUTHORIZED')
            if not contribution['order_id']:
                operation = self._prepare(lease, contribution, 'CREATE')
                if operation['provider_id']:
                    self._save_contribution(lease, contribution, order_id=operation['provider_id'],
                        create_request_id=operation['request_id'], state='AWAITING_APPROVAL')
            if not contribution['order_id']:
                if operation['state'] != 'PREPARED' and time.time() - operation['started_at'] >= CREATE_REPLAY_SECONDS:
                    self._state(lease, 'RECOVERY_REQUIRED', 'CREATE_REPLAY_WINDOW_EXPIRED')
                    raise BookingError('MERCHANT_REVIEW_REQUIRED')
                with self.store.engine.connect() as connection:
                    offer = connection.execute(select(catalog_offers).where(catalog_offers.c.id == purchase['offer_id'])).mappings().one()
                payload = dict(intent='AUTHORIZE', purchase_units=[dict(reference_id=contribution['id'],
                    custom_id=contribution['id'], description='Group share: ' + offer['title'],
                    amount=dict(currency_code=purchase['currency'], value=money(contribution['share_cents'])))])
                # Catalog operator labels are NOT PayPal account IDs. Standard
                # Checkout selects the OAuth app's seller without a payee override.
                result = self._network(lease, operation, lambda: self.paypal.create_order(payload, operation['request_id']))
                order_id = provider_id(result.get('id'))
                self._save_operation(lease, operation, provider_id=order_id, state='COMPLETED')
                self._save_contribution(lease, contribution, order_id=order_id,
                    create_request_id=operation['request_id'], state='AWAITING_APPROVAL')
            self._checked_observe(lease, purchase, contribution)
            self._refresh_waiting_state(lease)
        return dict(orderID=contribution['order_id'], shareCents=contribution['share_cents'],
            shareValue=money(contribution['share_cents']), currency=purchase['currency'], holdDeadline=purchase['hold_deadline'])

    def authorize(self, participant_id, group_id):
        purchase = self.purchase_for(participant_id, group_id)
        with claim_booking(self.store, purchase['id']) as lease:
            purchase, workflow, _ = self._records(purchase['id'])
            self._check_open(purchase, workflow)
            contribution = self._contribution(purchase['id'], participant_id)
            if not contribution['order_id']:
                raise BookingError('ORDER_NOT_INITIATED', 400)
            if not contribution['consent_given_at']:
                raise BookingError('CONSENT_REQUIRED', 400)
            self._checked_observe(lease, purchase, contribution)
            if not contribution['authorization_id']:
                if contribution['providerOrderStatus'] != 'APPROVED':
                    raise BookingError('BUYER_APPROVAL_REQUIRED', 409)
                operation = self._prepare(lease, contribution, 'AUTHORIZE', contribution['order_id'])
                if operation['state'] != 'PREPARED':
                    self._state(lease, 'RECOVERY_REQUIRED', 'AUTHORIZATION_OUTCOME_UNKNOWN')
                    raise BookingError('MERCHANT_REVIEW_REQUIRED')
                # Never use an enclosing order ID as an authorization fallback.
                result = self._network(lease, operation, lambda: self.paypal.authorize_order(contribution['order_id'], operation['request_id']))
                units = result.get('purchase_units') or []
                authorizations = units[0].get('payments', {}).get('authorizations', []) if len(units) == 1 else []
                if len(authorizations) == 1:
                    auth_id = provider_id(authorizations[0].get('id'))
                    self._save_operation(lease, operation, provider_id=auth_id)
                    self._save_contribution(lease, contribution, authorization_id=auth_id,
                        authorize_request_id=operation['request_id'])
                if result.get('id') != contribution['order_id']:
                    self._state(lease, 'RECOVERY_REQUIRED', 'AUTHORIZATION_RESPONSE_ORDER_MISMATCH')
                    raise BookingError('PAYMENT_RECOVERY_REQUIRED', 502)
                self._checked_observe(lease, purchase, contribution)
                if not contribution['authorization_id']:
                    self._state(lease, 'RECOVERY_REQUIRED', 'AUTHORIZATION_EVIDENCE_MISSING')
                    raise BookingError('PAYMENT_RECOVERY_REQUIRED', 502)
            self._refresh_waiting_state(lease)
        return self.booking.view(participant_id, group_id)

    def _refresh_waiting_state(self, lease):
        purchase, workflow, contributions = self._records(lease.purchase_id)
        if workflow['cancel_requested'] or purchase['state'] in TERMINAL:
            return
        uncertain = any(c['state'] in ('AUTHORIZATION_UNKNOWN', 'CAPTURE_UNKNOWN', 'CAPTURE_PENDING', 'CAPTURE_FAILED') for c in contributions)
        with self.store.engine.connect() as connection:
            uncertain = uncertain or bool(connection.execute(select(group_operations.c.id).where(
                group_operations.c.purchase_id == purchase['id'],
                group_operations.c.state.in_(('STARTED', 'UNKNOWN', 'PENDING', 'FAILED')))).first())
        if uncertain:
            self._state(lease, 'RECOVERY_REQUIRED', 'PROVIDER_OUTCOME_UNRESOLVED')
        elif all(c['state'] in ('AUTHORIZED', 'CAPTURED') for c in contributions):
            self._state(lease, 'FINALIZING', finalization_requested=1)
        else:
            self._state(lease, 'AWAITING_AUTHORIZATIONS')

    def reconcile(self, participant_id, group_id):
        purchase = self.purchase_for(participant_id, group_id)
        resume_approval = False
        resume_create = False
        with claim_booking(self.store, purchase['id']) as lease:
            purchase, workflow, _ = self._records(purchase['id'])
            if purchase['state'] in TERMINAL:
                return self.booking.view(participant_id, group_id)
            contribution = self._contribution(purchase['id'], participant_id)
            self._checked_observe(lease, purchase, contribution)
            if not contribution['order_id']:
                resume_create = bool(self._operation(contribution, 'CREATE') and contribution['consent_given_at'] and
                    not workflow['cancel_requested'] and purchase['hold_deadline'] > time.time())
                if not resume_create:
                    raise BookingError('ORDER_NOT_INITIATED', 400)
            operation = self._operation(contribution, 'AUTHORIZE')
            resume_approval = (contribution.get('providerOrderStatus') == 'APPROVED' and
                not contribution['authorization_id'] and contribution['consent_given_at'] and
                not workflow['cancel_requested'] and purchase['hold_deadline'] > time.time() and
                (not operation or operation['state'] == 'PREPARED'))
            self._refresh_waiting_state(lease)
        if resume_approval:
            return self.authorize(participant_id, group_id)
        if resume_create:
            self.initiate(participant_id, group_id)
            return self.booking.view(participant_id, group_id)
        return self.booking.view(participant_id, group_id)

    def _capture_one(self, lease, purchase, contribution):
        self._checked_observe(lease, purchase, contribution)
        if contribution['state'] == 'CAPTURED':
            return True
        operation = self._operation(contribution, 'CAPTURE')
        if operation and operation['state'] != 'PREPARED':
            self._state(lease, 'RECOVERY_REQUIRED', 'CAPTURE_OUTCOME_UNRESOLVED')
            return False
        if contribution['state'] != 'AUTHORIZED':
            self._state(lease, 'RECOVERY_REQUIRED', 'AUTHORIZATION_NOT_READY')
            return False
        operation = operation or self._prepare(lease, contribution, 'CAPTURE', contribution['authorization_id'])
        payload = dict(amount=dict(currency_code=purchase['currency'], value=money(contribution['share_cents'])), final_capture=True)
        result = self._network(lease, operation, lambda: self.paypal.capture_authorization(
            contribution['authorization_id'], payload, operation['request_id']))
        cap_id = provider_id(result.get('id'))
        # Save known provider ID even if a later validation/GET fails.
        self._save_operation(lease, operation, provider_id=cap_id)
        self._save_contribution(lease, contribution, capture_id=cap_id, capture_request_id=operation['request_id'])
        self._checked_observe(lease, purchase, contribution)
        if contribution['state'] != 'CAPTURED':
            self._state(lease, 'RECOVERY_REQUIRED', 'CAPTURE_NOT_COMPLETED')
            return False
        return True

    def _confirm(self, lease):
        purchase, workflow, contributions = self._records(lease.purchase_id)
        if workflow['cancel_requested'] or purchase['hold_deadline'] <= time.time():
            return False
        if not all(c['state'] == 'CAPTURED' and c['capture_id'] for c in contributions):
            return False
        if sum(c['share_cents'] for c in contributions) != purchase['total_cents']:
            raise BookingError('CONTRIBUTION_TOTAL_MISMATCH')
        with lease.write() as connection:
            for contribution in contributions:
                changed = connection.execute(update(catalog_resources).where(
                    catalog_resources.c.id == contribution['assigned_resource_id'],
                    catalog_resources.c.held_by_purchase_id == purchase['id'],
                    catalog_resources.c.state == 'HELD').values(state='BOOKED', held_until=None))
                if changed.rowcount != 1:
                    raise BookingError('RESOURCE_OWNERSHIP_LOST')
                connection.execute(insert(group_tickets).values(id=identifier(), purchase_id=purchase['id'],
                    contribution_id=contribution['id'], participant_id=contribution['participant_id'],
                    resource_id=contribution['assigned_resource_id'], ticket_code='TICKET-' + identifier().upper(), issued_at=time.time()))
            connection.execute(update(shared_purchases).where(shared_purchases.c.id == purchase['id']).values(state='CONFIRMED'))
            connection.execute(update(group_workflows).where(group_workflows.c.purchase_id == purchase['id']).values(error=None))
        return True

    def _complete(self, lease):
        purchase, workflow, contributions = self._records(lease.purchase_id)
        if purchase['hold_deadline'] <= time.time():
            self._state(lease, 'CANCELLING', 'HOLD_DEADLINE_EXPIRED', cancel_requested=1)
            return self._compensate(lease)
        # Validate the entire roster before starting any new capture. Otherwise
        # random contribution ordering can charge one member before discovering
        # a different member's mismatched merchant or order correlation.
        for contribution in contributions:
            self._checked_observe(lease, purchase, contribution)
        for contribution in contributions:
            try:
                operation = self._operation(contribution, 'CAPTURE')
                if operation and operation['state'] == 'FAILED':
                    self._state(lease, 'CANCELLING', operation['error'], cancel_requested=1)
                    return self._compensate(lease)
                if not self._capture_one(lease, purchase, contribution):
                    return False
            except BookingError as error:
                operation = self._operation(contribution, 'CAPTURE')
                # A definite rejection starts cancellation; uncertain captures
                # remain reserved until authenticated reconciliation resolves them.
                if operation and operation['state'] == 'FAILED':
                    self._state(lease, 'CANCELLING', operation['error'], cancel_requested=1)
                    self._compensate(lease)
                raise error
        if not self._confirm(lease):
            self._state(lease, 'CANCELLING', 'HOLD_DEADLINE_EXPIRED', cancel_requested=1)
            self._compensate(lease)
        return True

    def finalize(self, participant_id, group_id):
        purchase = self.purchase_for(participant_id, group_id, organizer=True)
        with claim_booking(self.store, purchase['id']) as lease:
            purchase, workflow, contributions = self._records(purchase['id'])
            if purchase['state'] == 'CONFIRMED':
                return self.booking.view(participant_id, group_id)
            self._check_open(purchase, workflow)
            if not all(c['state'] in ('AUTHORIZED', 'CAPTURED') for c in contributions):
                raise BookingError('ALL_AUTHORIZATIONS_REQUIRED', 400)
            self._state(lease, 'FINALIZING', finalization_requested=1)
            self._complete(lease)
        return self.booking.view(participant_id, group_id)

    def _refund(self, lease, purchase, contribution):
        operation = self._prepare(lease, contribution, 'REFUND', contribution['capture_id'])
        if operation['state'] == 'PREPARED':
            result = self._network(lease, operation, lambda: self.paypal.refund_capture(contribution['capture_id'], {}, operation['request_id']))
            self._save_operation(lease, operation, provider_id=provider_id(result.get('id')), state='PENDING')
        if not operation['provider_id']:
            self._state(lease, 'RECOVERY_REQUIRED', 'REFUND_OUTCOME_UNKNOWN', cancel_requested=1)
            return False
        lease.renew()
        refund = self.paypal.get_refund(operation['provider_id'])
        validate_refund(refund, operation, contribution, purchase)
        if refund.get('status') != 'COMPLETED':
            self._save_operation(lease, operation, state='PENDING', error='REFUND_NOT_COMPLETED')
            self._save_contribution(lease, contribution, state='REFUND_PENDING')
            return False
        self._save_operation(lease, operation, state='COMPLETED', error=None)
        self._save_contribution(lease, contribution, state='REFUNDED')
        return True

    def _void(self, lease, purchase, contribution):
        operation = self._prepare(lease, contribution, 'VOID', contribution['authorization_id'])
        if operation['state'] == 'PREPARED':
            self._network(lease, operation, lambda: self.paypal.void_authorization(contribution['authorization_id'], operation['request_id']))
        lease.renew()
        authorization = self.paypal.get_authorization(contribution['authorization_id'])
        # _compensate just validated this authorization's membership in its
        # authenticated order before entering this mutation.
        validate_authorization(authorization, contribution, purchase, listed_in_order=True)
        if authorization.get('status') != 'VOIDED':
            self._save_operation(lease, operation, state='UNKNOWN', error='VOID_NOT_CONFIRMED')
            return False
        self._save_operation(lease, operation, state='COMPLETED', provider_id=contribution['authorization_id'])
        self._save_contribution(lease, contribution, state='VOIDED')
        return True

    def _compensate(self, lease):
        purchase, _, contributions = self._records(lease.purchase_id)
        resolved = True
        for contribution in contributions:
            try:
                self._checked_observe(lease, purchase, contribution)
                if contribution['state'] == 'CAPTURED':
                    resolved = self._refund(lease, purchase, contribution) and resolved
                elif contribution['state'] == 'REFUNDED':
                    pass
                elif contribution['state'] in ('CAPTURE_UNKNOWN', 'CAPTURE_PENDING', 'AUTHORIZATION_UNKNOWN', 'REFUND_PENDING'):
                    resolved = False
                elif contribution['authorization_id']:
                    resolved = self._void(lease, purchase, contribution) and resolved
                elif self._operation(contribution, 'AUTHORIZE'):
                    resolved = False
                elif not contribution['order_id'] and self._operation(contribution, 'CREATE'):
                    # Unknown create could have produced an order. No new purchase.
                    resolved = False
                else:
                    self._save_contribution(lease, contribution, state='VOIDED')
            except (BookingError, PayPalError, KeyError, TypeError, ValueError) as error:
                if isinstance(error, BookingError) and error.issue == 'STALE_OPERATION':
                    raise
                resolved = False
                issue = error.issue if hasattr(error, 'issue') else 'INVALID_PROVIDER_RESPONSE'
                self._state(lease, 'RECOVERY_REQUIRED', issue, cancel_requested=1)
        if resolved:
            state = 'EXPIRED' if purchase['hold_deadline'] <= time.time() else 'CANCELLED'
            with lease.write() as connection:
                connection.execute(update(catalog_resources).where(catalog_resources.c.held_by_purchase_id == purchase['id'],
                    catalog_resources.c.state == 'HELD').values(state='FREE', held_by_purchase_id=None, held_until=None))
                connection.execute(update(shared_purchases).where(shared_purchases.c.id == purchase['id']).values(state=state))
                connection.execute(update(group_workflows).where(group_workflows.c.purchase_id == purchase['id']).values(error=None))
        else:
            self._state(lease, 'RECOVERY_REQUIRED', 'FINANCIAL_OBLIGATIONS_UNRESOLVED', cancel_requested=1)
        return resolved

    def cancel(self, participant_id, group_id):
        purchase = self.purchase_for(participant_id, group_id, organizer=True)
        with claim_booking(self.store, purchase['id']) as lease:
            purchase, _, _ = self._records(purchase['id'])
            if purchase['state'] == 'CONFIRMED':
                raise BookingError('CONFIRMED_BOOKING_CANNOT_BE_CANCELLED')
            if purchase['state'] not in ('CANCELLED', 'EXPIRED'):
                self._state(lease, 'CANCELLING', cancel_requested=1)
                self._compensate(lease)
        return self.booking.view(participant_id, group_id)

    def recover(self, participant_id, group_id):
        purchase = self.purchase_for(participant_id, group_id, organizer=True)
        self.recover_purchase(purchase['id'])
        return self.booking.view(participant_id, group_id)

    def recover_purchase(self, purchase_id):
        """One bounded server-side pass. Scheduler/CLI may call again later."""
        with claim_booking(self.store, purchase_id) as lease:
            purchase, workflow, contributions = self._records(purchase_id)
            if purchase['state'] in TERMINAL:
                return
            if workflow['cancel_requested'] or purchase['hold_deadline'] <= time.time():
                self._state(lease, 'CANCELLING', cancel_requested=1)
                self._compensate(lease)
                return
            for contribution in contributions:
                self._checked_observe(lease, purchase, contribution)
            self._refresh_waiting_state(lease)
            purchase, workflow, contributions = self._records(purchase_id)
            if workflow['finalization_requested']:
                if any(c['state'] in ('CAPTURE_FAILED', 'VOIDED') for c in contributions):
                    self._state(lease, 'CANCELLING', cancel_requested=1)
                    self._compensate(lease)
                else:
                    self._complete(lease)

    def recover_pending(self, limit=20):
        with self.store.engine.connect() as connection:
            purchase_ids = connection.execute(select(shared_purchases.c.id).where(
                shared_purchases.c.state.in_(('AWAITING_AUTHORIZATIONS', 'FINALIZING', 'RECOVERY_REQUIRED', 'CANCELLING'))
            ).order_by(shared_purchases.c.created_at).limit(limit)).scalars().all()
        result = dict(inspected=0, unresolved=0)
        for purchase_id in purchase_ids:
            result['inspected'] += 1
            try:
                self.recover_purchase(purchase_id)
                if self._records(purchase_id)[0]['state'] in ('RECOVERY_REQUIRED', 'CANCELLING'):
                    result['unresolved'] += 1
            except (BookingError, PayPalError):
                result['unresolved'] += 1
        return result
