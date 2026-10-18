"""Adversarial group-payment contracts; all provider operations are fake."""
import copy
import io
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_phase4_fulfillment as fulfillment
from sqlalchemy import event, insert, select, update

from booking_errors import BookingError
from booking_lease import claim_booking
from payments import PayPal, PayPalError
from server import create_app
from storage import (Store, catalog_resources, group_operations, group_tickets,
                     group_workflows, purchase_contributions, shared_purchases, versions)


class BookingSafetyTests(unittest.TestCase):
    setUp = fulfillment.Phase4FulfillmentTests.setUp
    tearDown = fulfillment.Phase4FulfillmentTests.tearDown
    post = fulfillment.Phase4FulfillmentTests.post
    create_authorized_group = fulfillment.Phase4FulfillmentTests.create_authorized_group

    def frozen_unpaid_group(self):
        group = self.post(self.organizer, '/api/groups', {'name': 'Saved payment'}).json
        self.post(self.member, '/api/groups/join', {'inviteToken': group['inviteURL'].split('invite=')[1]})
        group_id = group['id']
        frozen = self.post(self.organizer, f'/api/groups/{group_id}/freeze', dict(offerID='movie-cosmic-odyssey-fri',
            resourceIDs=['res-movie-cosmic-odyssey-fri-A1', 'res-movie-cosmic-odyssey-fri-A2']))
        self.assertEqual(frozen.status_code, 200)
        self.post(self.organizer, f'/api/groups/{group_id}/booking/consent', {})
        return group_id

    def saved(self, group_id):
        return self.organizer.get(f'/api/groups/{group_id}/booking').json

    def finalize(self, group_id):
        return self.post(self.organizer, f'/api/groups/{group_id}/finalize', {})

    def recover(self, group_id):
        return self.post(self.organizer, f'/api/groups/{group_id}/recover', {})

    def resources(self):
        with self.app.extensions['store'].engine.connect() as connection:
            return list(connection.execute(select(catalog_resources.c.state).where(
                catalog_resources.c.id.in_(['res-movie-cosmic-odyssey-fri-A1', 'res-movie-cosmic-odyssey-fri-A2']))).scalars())

    def test_pending_capture_keeps_tickets_locked_then_reconciles_without_recapture(self):
        group_id = self.create_authorized_group()
        self.fake.authorization_capture_status = 'PENDING'
        self.assertEqual(self.finalize(group_id).json['state'], 'RECOVERY_REQUIRED')
        self.assertEqual(self.organizer.get(f'/api/groups/{group_id}/ticket').status_code, 404)
        self.assertEqual(self.resources(), ['HELD', 'HELD'])
        self.assertEqual(self.fake.capture_auth_calls, 1)
        self.fake.captures['CAP1']['status'] = 'COMPLETED'
        self.fake.authorization_capture_status = 'COMPLETED'
        self.assertEqual(self.recover(group_id).json['state'], 'CONFIRMED')
        self.assertEqual(self.fake.capture_auth_calls, 2)

    def test_mismatched_capture_amount_or_currency_never_unlocks(self):
        group_id = self.create_authorized_group()
        original = self.fake.capture_authorization
        def wrong_capture(*args):
            result = original(*args)
            self.fake.captures[result['id']]['amount'] = dict(value='0.01', currency_code='EUR')
            return result
        self.fake.capture_authorization = wrong_capture
        self.assertEqual(self.finalize(group_id).status_code, 502)
        self.assertEqual(self.saved(group_id)['state'], 'RECOVERY_REQUIRED')
        self.assertEqual(self.organizer.get(f'/api/groups/{group_id}/ticket').status_code, 404)

    def test_lost_capture_response_is_recovered_from_provider_not_replayed(self):
        group_id = self.create_authorized_group()
        self.fake.lose_capture_auth_response = True
        self.assertEqual(self.finalize(group_id).status_code, 502)
        self.assertEqual(len(self.fake.captures), 1)
        self.assertEqual(getattr(self.fake, 'refund_calls', 0), 0)
        self.fake.lose_capture_auth_response = False
        self.assertEqual(self.recover(group_id).json['state'], 'CONFIRMED')
        self.assertEqual(len(self.fake.captures), 2)
        self.assertEqual(self.fake.capture_auth_calls, 2)

    def test_unknown_capture_with_no_provider_id_stays_visible_after_expiry(self):
        group_id = self.create_authorized_group()
        self.fake.fail_capture_auth = True
        self.finalize(group_id)
        store = self.app.extensions['store']
        with store.engine.begin() as connection:
            connection.execute(update(shared_purchases).values(hold_deadline=1))
        self.recover(group_id)
        saved = self.saved(group_id)
        self.assertTrue(saved['hasBooking'])
        self.assertEqual(saved['state'], 'RECOVERY_REQUIRED')
        self.assertEqual(self.fake.capture_auth_calls, 1)
        self.assertEqual(self.resources(), ['HELD', 'HELD'])

    def test_refund_and_void_failures_never_claim_cancelled_or_refunded(self):
        group_id = self.create_authorized_group()
        original = self.fake.capture_authorization
        def decline_second(*args):
            if getattr(self.fake, 'capture_auth_calls', 0) == 1:
                raise PayPalError('INSTRUMENT_DECLINED', uncertain=False)
            return original(*args)
        self.fake.capture_authorization = decline_second
        self.fake.fail_refund = self.fake.fail_void = True
        result = self.finalize(group_id)
        self.assertNotIn('REFUNDED', result.json['error'])
        saved = self.saved(group_id)
        self.assertEqual(saved['state'], 'RECOVERY_REQUIRED')
        self.assertTrue(saved['hasBooking'])
        self.assertEqual(self.resources(), ['HELD', 'HELD'])

    def test_pending_refund_id_survives_restart_and_reconciles_to_completion(self):
        group_id = self.create_authorized_group()
        original = self.fake.capture_authorization
        def decline_second(*args):
            if getattr(self.fake, 'capture_auth_calls', 0) == 1:
                raise PayPalError('INSTRUMENT_DECLINED', uncertain=False)
            return original(*args)
        self.fake.capture_authorization = decline_second
        self.fake.refund_status = 'PENDING'
        self.finalize(group_id)
        self.assertEqual(self.saved(group_id)['state'], 'RECOVERY_REQUIRED')
        self.assertEqual(self.resources(), ['HELD', 'HELD'])
        self.fake.refunds['REF1']['status'] = 'COMPLETED'
        restarted = create_app(self.config, paypal=self.fake)
        try:
            restarted.extensions['booking'].payments.recover_pending()
        finally:
            restarted.extensions['store'].engine.dispose()
        self.assertEqual(self.saved(group_id)['state'], 'CANCELLED')
        self.assertEqual(self.fake.refund_calls, 1)
        self.assertEqual(self.resources(), ['FREE', 'FREE'])

    def test_confirmed_booking_rejects_member_and_organizer_cancellation(self):
        group_id = self.create_authorized_group()
        self.finalize(group_id)
        self.assertEqual(self.post(self.member, f'/api/groups/{group_id}/booking/void', {}).status_code, 403)
        self.assertEqual(self.post(self.organizer, f'/api/groups/{group_id}/booking/void', {}).status_code, 409)
        self.assertEqual(self.resources(), ['BOOKED', 'BOOKED'])
        self.assertEqual(self.organizer.get(f'/api/groups/{group_id}/ticket').status_code, 200)

    def test_expired_authorizations_are_voided_by_runner_without_capture(self):
        group_id = self.create_authorized_group()
        with self.app.extensions['store'].engine.begin() as connection:
            connection.execute(update(shared_purchases).values(hold_deadline=1))
        self.app.extensions['booking'].payments.recover_pending()
        self.assertEqual(self.saved(group_id)['state'], 'EXPIRED')
        self.assertEqual(getattr(self.fake, 'capture_auth_calls', 0), 0)
        self.assertEqual(self.fake.void_calls, 2)
        self.assertEqual(self.resources(), ['FREE', 'FREE'])

    def test_all_authorizations_resume_server_finalization_without_browser(self):
        group_id = self.create_authorized_group()
        self.app.extensions['booking'].payments.recover_pending()
        self.assertEqual(self.saved(group_id)['state'], 'CONFIRMED')
        self.assertEqual(self.fake.capture_auth_calls, 2)

    def test_concurrent_finalization_has_one_owner_and_one_ticket_per_member(self):
        group_id = self.create_authorized_group()
        service = self.app.extensions['booking']
        participant = self.organizer.get('/api/config').json['participantID']
        original = self.fake.capture_authorization
        def slow(*args):
            time.sleep(0.05)
            return original(*args)
        self.fake.capture_authorization = slow
        def finalize():
            try:
                return service.finalize_booking(participant, group_id)['state']
            except BookingError as error:
                return error.issue
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: finalize(), range(2)))
        self.assertIn('CONFIRMED', results)
        self.assertEqual(self.fake.capture_auth_calls, 2)
        with self.app.extensions['store'].engine.connect() as connection:
            self.assertEqual(len(connection.execute(select(group_tickets)).all()), 2)

    def test_expired_worker_cannot_write_or_dispatch_capture(self):
        group_id = self.create_authorized_group()
        purchase_id = self.saved(group_id)['purchaseID']
        store = self.app.extensions['store']
        with claim_booking(store, purchase_id) as lease:
            with store.engine.begin() as connection:
                connection.execute(update(group_workflows).values(lease_until=1))
            with self.assertRaises(BookingError):
                self.app.extensions['booking'].payments._complete(lease)
        self.assertEqual(getattr(self.fake, 'capture_auth_calls', 0), 0)

    def test_known_capture_operation_id_survives_crash_before_contribution_save(self):
        group_id = self.create_authorized_group()
        service = self.app.extensions['booking'].payments
        original = service._save_operation
        def crash(lease, operation, **values):
            original(lease, operation, **values)
            if operation['kind'] == 'CAPTURE' and values.get('provider_id'):
                raise SystemExit('simulated process stop')
        service._save_operation = crash
        with self.assertRaises(SystemExit):
            self.finalize(group_id)
        service._save_operation = original
        self.fake.hide_order_captures = True
        recovery = self.recover(group_id)
        self.assertEqual(recovery.status_code, 200, recovery.json)
        self.assertEqual(recovery.json['state'], 'CONFIRMED')
        self.assertEqual(self.fake.capture_auth_calls, 2)

    def test_group_provider_calls_never_hold_database_transactions(self):
        group_id = self.create_authorized_group()
        engine = self.app.extensions['store'].engine
        active = set()
        def begin(connection): active.add(id(connection))
        def end(connection): active.discard(id(connection))
        event.listen(engine, 'begin', begin)
        event.listen(engine, 'commit', end)
        event.listen(engine, 'rollback', end)
        originals = {}
        try:
            for name in ('get_order', 'get_authorization', 'get_capture', 'capture_authorization'):
                originals[name] = getattr(self.fake, name)
                def checked(*args, original=originals[name]):
                    self.assertFalse(active, 'transaction held across provider call')
                    return original(*args)
                setattr(self.fake, name, checked)
            self.assertEqual(self.finalize(group_id).json['state'], 'CONFIRMED')
        finally:
            for name, original in originals.items(): setattr(self.fake, name, original)
            event.remove(engine, 'begin', begin)
            event.remove(engine, 'commit', end)
            event.remove(engine, 'rollback', end)

    def test_legacy_revision_three_payments_are_preserved_and_quarantined(self):
        group_id = self.create_authorized_group()
        self.finalize(group_id)
        store = self.app.extensions['store']
        with store.engine.begin() as connection:
            connection.execute(group_operations.delete())
            connection.execute(group_workflows.delete())
            connection.execute(update(versions).values(revision=3))
        store.migrate(target=4)
        store.migrate(target=4)
        self.assertEqual(self.saved(group_id)['state'], 'RECOVERY_REQUIRED')
        self.assertEqual(self.organizer.get(f'/api/groups/{group_id}/ticket').status_code, 409)
        with store.engine.connect() as connection:
            self.assertEqual(len(connection.execute(select(group_tickets)).all()), 2)
            self.assertTrue(all(connection.execute(select(purchase_contributions.c.capture_id)).scalars()))

    def test_unapproved_order_cannot_authorize_and_payload_has_no_fictional_payee(self):
        group = self.post(self.organizer, '/api/groups', {'name': 'Approval boundary'}).json
        self.post(self.member, '/api/groups/join', {'inviteToken': group['inviteURL'].split('invite=')[1]})
        group_id = group['id']
        self.post(self.organizer, f'/api/groups/{group_id}/freeze', dict(offerID='movie-cosmic-odyssey-fri',
            resourceIDs=['res-movie-cosmic-odyssey-fri-A1','res-movie-cosmic-odyssey-fri-A2']))
        self.post(self.organizer, f'/api/groups/{group_id}/booking/consent', {})
        original = self.fake.create_order
        def inspect_payload(payload, key):
            self.assertNotIn('payee', payload['purchase_units'][0])
            self.assertLessEqual(len(key), 36)
            return original(payload, key)
        self.fake.create_order = inspect_payload
        order = self.post(self.organizer, f'/api/groups/{group_id}/contributions/order', {}).json
        response = self.post(self.organizer, f'/api/groups/{group_id}/contributions/authorize', {})
        self.assertEqual(response.json['error'], 'BUYER_APPROVAL_REQUIRED')
        self.assertEqual(getattr(self.fake, 'authorize_calls', 0), 0)
        self.fake.approve(order['orderID'])
        self.assertEqual(self.post(self.organizer, f'/api/groups/{group_id}/contributions/reconcile', {}).json['myShare']['state'], 'AUTHORIZED')

    def test_provider_void_http_204_is_successful_empty_response(self):
        class Response(io.BytesIO):
            status = 204
            def __enter__(self): return self
            def __exit__(self, *args): self.close()
        with patch('payments.urllib.request.urlopen', return_value=Response(b'')):
            self.assertEqual(PayPal('test','test')._request('POST', '/test', {}), {})

    def test_unlinked_authorization_is_not_accepted_when_order_omits_it(self):
        group_id = self.create_authorized_group()
        original = self.fake.get_order
        def omit_authorization(order_id):
            order = original(order_id)
            order['purchase_units'][0]['payments'].pop('authorizations', None)
            return order
        self.fake.get_order = omit_authorization
        self.assertEqual(self.finalize(group_id).status_code, 502)
        self.assertEqual(self.saved(group_id)['error'], 'AUTHORIZATION_LINKAGE_MISSING')
        self.assertEqual(getattr(self.fake, 'capture_auth_calls', 0), 0)
        self.assertEqual(self.organizer.get(f'/api/groups/{group_id}/ticket').status_code, 404)

    def test_provider_order_merchant_and_contribution_tampering_prevent_capture(self):
        group_id = self.create_authorized_group()
        payments = self.app.extensions['booking'].payments
        purchase = payments.purchase_for(self.organizer.get('/api/config').json['participantID'], group_id)
        # Target the last capture candidate so a missing roster-wide preflight
        # deterministically charges an earlier member before detecting the error.
        contributions = payments._records(purchase['id'])[2]
        order = self.fake.orders[contributions[-1]['order_id']]
        unit = order['purchase_units'][0]
        unit['payee']['merchant_id'] = 'OTHERSELLER'
        self.assertEqual(self.finalize(group_id).status_code, 502)
        self.assertEqual(getattr(self.fake, 'capture_auth_calls', 0), 0)
        unit['payee']['merchant_id'] = 'MERCHANT123'
        unit['custom_id'] = 'another-contribution'
        self.recover(group_id)
        self.assertEqual(self.saved(group_id)['error'], 'CONTRIBUTION_CORRELATION_MISMATCH')
        self.assertEqual(getattr(self.fake, 'capture_auth_calls', 0), 0)

    def test_get_polling_never_dispatches_financial_or_reconciliation_calls(self):
        group_id = self.create_authorized_group()
        before = (self.fake.get_calls, getattr(self.fake, 'capture_auth_calls', 0),
            getattr(self.fake, 'void_calls', 0), getattr(self.fake, 'refund_calls', 0))
        for _ in range(3):
            self.assertEqual(self.organizer.get(f'/api/groups/{group_id}/booking').status_code, 200)
            self.assertEqual(self.organizer.get(f'/api/groups/{group_id}').status_code, 200)
        after = (self.fake.get_calls, getattr(self.fake, 'capture_auth_calls', 0),
            getattr(self.fake, 'void_calls', 0), getattr(self.fake, 'refund_calls', 0))
        self.assertEqual(before, after)

    def test_unknown_create_resumes_same_request_from_owner_recheck(self):
        group_id = self.frozen_unpaid_group()
        self.fake.fail_create = True
        self.assertEqual(self.post(self.organizer, f'/api/groups/{group_id}/contributions/order', {}).status_code, 502)
        self.assertEqual(self.saved(group_id)['state'], 'RECOVERY_REQUIRED')
        self.fake.fail_create = False
        response = self.post(self.organizer, f'/api/groups/{group_id}/contributions/reconcile', {})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['state'], 'AWAITING_AUTHORIZATIONS')
        self.assertEqual(len(self.fake.create_keys), 1)
        with self.app.extensions['store'].engine.connect() as connection:
            operation = connection.execute(select(group_operations).where(group_operations.c.kind == 'CREATE')).mappings().one()
            self.assertEqual(operation['request_id'], next(iter(self.fake.create_keys)))

    def test_known_create_id_survives_crash_and_expired_reservation(self):
        group_id = self.frozen_unpaid_group()
        service = self.app.extensions['booking'].payments
        original = service._save_operation
        def crash(lease, operation, **values):
            original(lease, operation, **values)
            if operation['kind'] == 'CREATE' and values.get('provider_id'):
                raise SystemExit('simulated process stop')
        service._save_operation = crash
        with self.assertRaises(SystemExit):
            self.post(self.organizer, f'/api/groups/{group_id}/contributions/order', {})
        service._save_operation = original
        with self.app.extensions['store'].engine.begin() as connection:
            connection.execute(update(shared_purchases).values(hold_deadline=1))
        self.assertEqual(self.recover(group_id).json['state'], 'EXPIRED')
        self.assertEqual(self.fake.create_calls, 1)
        self.assertEqual(self.resources(), ['FREE', 'FREE'])

    def test_progress_sharing_requires_the_other_members_opt_in(self):
        group_id = self.frozen_unpaid_group()
        saved = self.saved(group_id)
        self.assertEqual(len(saved['rosterProgress']), 1)
        owner_id = self.organizer.get('/api/config').json['participantID']
        self.assertEqual(saved['rosterProgress'][0]['participantID'], owner_id)
        self.assertFalse(self.organizer.get(f'/api/groups/{group_id}').json['myProfile']['shareProgress'])

    def test_simultaneous_groups_cannot_both_hold_the_same_resources(self):
        first = self.post(self.organizer, '/api/groups', {'name': 'First'}).json
        second = self.post(self.outsider, '/api/groups', {'name': 'Second'}).json
        self.post(self.member, '/api/groups/join', {'inviteToken': first['inviteURL'].split('invite=')[1]})
        self.post(self.member, '/api/groups/join', {'inviteToken': second['inviteURL'].split('invite=')[1]})
        service = self.app.extensions['booking']
        owners = [self.organizer.get('/api/config').json['participantID'], self.outsider.get('/api/config').json['participantID']]
        def freeze(index):
            try:
                service.freeze(owners[index], (first,second)[index]['id'], 'movie-cosmic-odyssey-fri',
                    ['res-movie-cosmic-odyssey-fri-A1','res-movie-cosmic-odyssey-fri-A2'])
                return 'HELD'
            except BookingError as error:
                return error.issue
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(freeze, range(2)))
        self.assertCountEqual(outcomes, ['HELD', 'SEAT_UNAVAILABLE'])
        with self.app.extensions['store'].engine.connect() as connection:
            self.assertEqual(len(connection.execute(select(shared_purchases)).all()), 1)
            self.assertEqual(len(connection.execute(select(purchase_contributions)).all()), 2)
