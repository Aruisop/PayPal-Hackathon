"""Group reservations and private views; payment orchestration lives separately."""
import time
from datetime import datetime, timezone

from sqlalchemy import insert, select, update

from app.shared.errors import BookingError
from app.shared.storage import (catalog_offers, catalog_resources, group_member_profiles,
                     group_memberships, group_workflows, group_tickets, identifier,
                     money, purchase_contributions, shared_purchases,
                     split_equal_cents, workshop_groups)

OPEN_STATES = ('AWAITING_AUTHORIZATIONS', 'FINALIZING', 'RECOVERY_REQUIRED', 'CANCELLING', 'CONFIRMED')


def member_group(connection, participant_id, group_id, organizer=False):
    group = connection.execute(select(workshop_groups).join(group_memberships,
        group_memberships.c.group_id == workshop_groups.c.id).where(
        workshop_groups.c.id == group_id,
        group_memberships.c.participant_id == participant_id)).mappings().first()
    if not group:
        raise BookingError('GROUP_NOT_FOUND', 404)
    if organizer and group['organizer_id'] != participant_id:
        raise BookingError('ORGANIZER_REQUIRED', 403)
    return group


def latest_purchase(connection, group_id):
    row = connection.execute(select(shared_purchases).where(
        shared_purchases.c.group_id == group_id).order_by(
        shared_purchases.c.created_at.desc(), shared_purchases.c.id)).mappings().first()
    return dict(row) if row else None


class CollabBooking:
    def __init__(self, store, origin, paypal=None):
        from .payments import GroupPayments
        from app.planning.service import Planning
        self.store, self.origin, self.paypal = store, origin, paypal
        self.planning = Planning(store)
        self.payments = GroupPayments(self, paypal)

    def set_profile(self, participant_id, group_id, alias, consent=False):
        if not isinstance(alias, str) or not alias.strip() or len(alias.strip()) > 60:
            raise BookingError('INVALID_ALIAS', 400)
        with self.store.engine.begin() as connection:
            member_group(connection, participant_id, group_id)
            connection.execute(update(workshop_groups).where(workshop_groups.c.id == group_id).values(id=group_id))
            active = latest_purchase(connection, group_id)
            if active and active['state'] in OPEN_STATES:
                raise BookingError('ROSTER_ALREADY_FROZEN')
            existing = connection.execute(select(group_member_profiles.c.id).where(
                group_member_profiles.c.group_id == group_id,
                group_member_profiles.c.participant_id == participant_id)).scalar()
            values = dict(alias=alias.strip(), consent_coarse_progress=int(bool(consent)), updated_at=time.time())
            if existing:
                connection.execute(update(group_member_profiles).where(group_member_profiles.c.id == existing).values(**values))
            else:
                connection.execute(insert(group_member_profiles).values(id=identifier(), group_id=group_id,
                    participant_id=participant_id, **values))
        return dict(participantID=participant_id, alias=alias.strip())

    def _selection(self, connection, group_id, offer_id, resource_ids):
        members = connection.execute(select(group_memberships.c.participant_id).where(
            group_memberships.c.group_id == group_id).order_by(
            group_memberships.c.joined_at, group_memberships.c.id)).scalars().all()
        if not 2 <= len(members) <= 4:
            raise BookingError('GROUP_SIZE_UNSUPPORTED', 400)
        offer = connection.execute(select(catalog_offers).where(catalog_offers.c.id == offer_id)).mappings().first()
        if not offer:
            raise BookingError('OFFER_NOT_FOUND', 404)
        if datetime.fromisoformat(offer['schedule_time']).astimezone(timezone.utc) <= datetime.now(timezone.utc):
            raise BookingError('OFFER_EXPIRED')
        if (not isinstance(resource_ids, list) or len(resource_ids) != len(members) or
                any(not isinstance(value, str) for value in resource_ids) or len(set(resource_ids)) != len(resource_ids)):
            raise BookingError('RESOURCE_COUNT_MISMATCH', 400)
        resources = connection.execute(select(catalog_resources).where(
            catalog_resources.c.id.in_(resource_ids), catalog_resources.c.offer_id == offer_id)).mappings().all()
        if len(resources) != len(resource_ids):
            raise BookingError('INVALID_RESOURCES', 400)
        if any(resource['state'] != 'FREE' for resource in resources):
            raise BookingError('SEAT_UNAVAILABLE')
        if offer['domain'] == 'movie':
            columns = sorted(resource['col_number'] for resource in resources)
            if len({r['row_label'] for r in resources}) != 1 or columns[-1] - columns[0] != len(columns) - 1:
                raise BookingError('ADJACENT_SEATS_REQUIRED', 400)
        total = offer['price_minor'] * len(members) if offer['domain'] == 'movie' else offer['price_minor']
        if total <= 0 or offer['currency'] != 'USD':
            raise BookingError('INVALID_CATALOG_QUOTE')
        self.planning.validate_selection(connection, group_id, offer_id, resource_ids)
        return members, dict(offer), split_equal_cents(total, members), total

    def quote(self, participant_id, group_id, offer_id, selected_resource_ids=None):
        with self.store.engine.connect() as connection:
            member_group(connection, participant_id, group_id)
            if selected_resource_ids is None:
                count = len(connection.execute(select(group_memberships.c.id).where(
                    group_memberships.c.group_id == group_id)).all())
                free = connection.execute(select(catalog_resources).where(
                    catalog_resources.c.offer_id == offer_id, catalog_resources.c.state == 'FREE').order_by(
                    catalog_resources.c.row_label, catalog_resources.c.col_number)).mappings().all()
                selected_resource_ids = [row['id'] for row in free[:count]]
            members, offer, shares, total = self._selection(connection, group_id, offer_id, selected_resource_ids)
        return dict(offerID=offer_id, domain=offer['domain'], title=offer['title'], scheduleTime=offer['schedule_time'],
            totalCents=total, totalValue=money(total), currency=offer['currency'], memberCount=len(members),
            shares=[dict(participantID=pid, shareCents=value, shareValue=money(value)) for pid, value in shares.items()],
            policy='all_or_nothing_refund', roundingRule='Remainder cents assigned in frozen roster order.')

    def freeze(self, participant_id, group_id, offer_id, selected_resource_ids):
        with self.store.engine.begin() as connection:
            member_group(connection, participant_id, group_id, organizer=True)
            # Join, freeze and profile updates serialize on the same parent row.
            connection.execute(update(workshop_groups).where(workshop_groups.c.id == group_id).values(id=group_id))
            prior = latest_purchase(connection, group_id)
            if prior and prior['state'] not in ('CANCELLED', 'EXPIRED'):
                raise BookingError('ROSTER_ALREADY_FROZEN')
            if prior:
                workflow = connection.execute(select(group_workflows).where(
                    group_workflows.c.purchase_id == prior['id'])).mappings().one()
                if workflow['review_required']:
                    raise BookingError('LEGACY_PURCHASE_REQUIRES_REVIEW')
            members, offer, shares, total = self._selection(connection, group_id, offer_id, selected_resource_ids)
            now, purchase_id = time.time(), identifier()
            deadline = now + 900
            connection.execute(insert(shared_purchases).values(id=purchase_id, group_id=group_id,
                offer_id=offer_id, state='AWAITING_AUTHORIZATIONS', total_cents=total, currency=offer['currency'],
                frozen_at=now, hold_deadline=deadline, policy='all_or_nothing_refund', created_at=now))
            connection.execute(insert(group_workflows).values(purchase_id=purchase_id, lease_until=0,
                merchant_id=getattr(self.paypal, 'merchant_id', '') or '', cancel_requested=0,
                review_required=0, updated_at=now))
            for resource_id in sorted(selected_resource_ids):
                changed = connection.execute(update(catalog_resources).where(
                    catalog_resources.c.id == resource_id, catalog_resources.c.state == 'FREE').values(
                    state='HELD', held_by_purchase_id=purchase_id, held_until=deadline))
                if changed.rowcount != 1:
                    raise BookingError('SEAT_UNAVAILABLE')
            profiles = dict(connection.execute(select(group_member_profiles.c.participant_id,
                group_member_profiles.c.alias).where(group_member_profiles.c.group_id == group_id)).all())
            for index, pid in enumerate(members):
                connection.execute(insert(purchase_contributions).values(id=identifier(), purchase_id=purchase_id,
                    participant_id=pid, alias=profiles.get(pid, f'Member {index + 1}'), share_cents=shares[pid],
                    assigned_resource_id=selected_resource_ids[index], state='PENDING_CONSENT', created_at=now))
        return self.view(participant_id, group_id)

    def freeze_merchant_checkout(self, participant_id, group_id):
        """Hold the server-selected merchant resources after its fixed roster joins.

        Merchant mode intentionally bypasses preference matching, not quote,
        inventory, consent, payment-evidence, or ownership checks.
        """
        with self.store.engine.begin() as connection:
            group = member_group(connection, participant_id, group_id, organizer=True)
            if group['checkout_mode'] != 'merchant' or not group['merchant_offer_id']:
                raise BookingError('MERCHANT_CHECKOUT_REQUIRED', 409)
            connection.execute(update(workshop_groups).where(workshop_groups.c.id == group_id).values(id=group_id))
            prior = latest_purchase(connection, group_id)
            if prior and prior['state'] not in ('CANCELLED', 'EXPIRED'):
                raise BookingError('ROSTER_ALREADY_FROZEN')
            members = connection.execute(select(group_memberships.c.participant_id).where(
                group_memberships.c.group_id == group_id).order_by(
                group_memberships.c.joined_at, group_memberships.c.id)).scalars().all()
            if len(members) != group['target_member_count'] or not 1 <= len(members) <= 4:
                raise BookingError('MERCHANT_ROSTER_INCOMPLETE', 409)
            offer = connection.execute(select(catalog_offers).where(
                catalog_offers.c.id == group['merchant_offer_id'])).mappings().first()
            if not offer or offer['currency'] != 'USD' or datetime.fromisoformat(offer['schedule_time']).astimezone(timezone.utc) <= datetime.now(timezone.utc):
                raise BookingError('MERCHANT_OFFER_UNAVAILABLE', 409)
            resources = connection.execute(select(catalog_resources).where(
                catalog_resources.c.offer_id == offer['id'], catalog_resources.c.state == 'FREE').order_by(
                catalog_resources.c.row_label, catalog_resources.c.col_number).limit(len(members))).mappings().all()
            if len(resources) != len(members):
                raise BookingError('SEAT_UNAVAILABLE')
            if offer['domain'] == 'movie':
                columns = [resource['col_number'] for resource in resources]
                if len({resource['row_label'] for resource in resources}) != 1 or columns[-1] - columns[0] != len(columns) - 1:
                    raise BookingError('ADJACENT_SEATS_REQUIRED', 409)
                total = offer['price_minor'] * len(members)
            else:
                total = offer['price_minor']
            if total <= 0:
                raise BookingError('INVALID_CATALOG_QUOTE')
            now, purchase_id, deadline = time.time(), identifier(), time.time() + 900
            connection.execute(insert(shared_purchases).values(id=purchase_id, group_id=group_id,
                offer_id=offer['id'], state='AWAITING_AUTHORIZATIONS', total_cents=total, currency=offer['currency'],
                frozen_at=now, hold_deadline=deadline, policy='all_or_nothing_refund', created_at=now))
            connection.execute(insert(group_workflows).values(purchase_id=purchase_id, lease_until=0,
                merchant_id=getattr(self.paypal, 'merchant_id', '') or '', cancel_requested=0,
                review_required=0, updated_at=now))
            profiles = dict(connection.execute(select(group_member_profiles.c.participant_id,
                group_member_profiles.c.alias).where(group_member_profiles.c.group_id == group_id)).all())
            shares = split_equal_cents(total, members)
            for index, (pid, resource) in enumerate(zip(members, resources)):
                changed = connection.execute(update(catalog_resources).where(
                    catalog_resources.c.id == resource['id'], catalog_resources.c.state == 'FREE').values(
                    state='HELD', held_by_purchase_id=purchase_id, held_until=deadline))
                if changed.rowcount != 1:
                    raise BookingError('SEAT_UNAVAILABLE')
                connection.execute(insert(purchase_contributions).values(id=identifier(), purchase_id=purchase_id,
                    participant_id=pid, alias=profiles.get(pid, f'Member {index + 1}'), share_cents=shares[pid],
                    assigned_resource_id=resource['id'], state='PENDING_CONSENT', created_at=now))
        return self.view(participant_id, group_id)

    def view(self, participant_id, group_id):
        with self.store.engine.connect() as connection:
            group = member_group(connection, participant_id, group_id)
            purchase = latest_purchase(connection, group_id)
            if not purchase:
                return dict(groupID=group_id, hasBooking=False)
            workflow = connection.execute(select(group_workflows).where(
                group_workflows.c.purchase_id == purchase['id'])).mappings().one()
            offer = connection.execute(select(catalog_offers).where(catalog_offers.c.id == purchase['offer_id'])).mappings().one()
            contributions = connection.execute(select(purchase_contributions).where(
                purchase_contributions.c.purchase_id == purchase['id']).order_by(purchase_contributions.c.created_at,
                purchase_contributions.c.id)).mappings().all()
            profiles = {row['participant_id']: row for row in connection.execute(select(group_member_profiles).where(
                group_member_profiles.c.group_id == group_id)).mappings()}
            own, progress = None, []
            for contribution in contributions:
                mine = contribution['participant_id'] == participant_id
                profile = profiles.get(contribution['participant_id'])
                if mine or (profile and profile['consent_coarse_progress']):
                    progress.append(dict(participantID=contribution['participant_id'], alias=contribution['alias'],
                        state=contribution['state'], hasConsented=bool(contribution['consent_given_at']),
                        hasAuthorized=contribution['state'] in ('AUTHORIZED', 'CAPTURED'),
                        shareValue=money(contribution['share_cents'])))
                if mine:
                    label = connection.execute(select(catalog_resources.c.label).where(
                        catalog_resources.c.id == contribution['assigned_resource_id'])).scalar()
                    own = dict(contributionID=contribution['id'], alias=contribution['alias'],
                        shareCents=contribution['share_cents'], shareValue=money(contribution['share_cents']),
                        assignedResource=label, state=contribution['state'], orderID=contribution['order_id'],
                        authorizationID=contribution['authorization_id'], captureID=contribution['capture_id'],
                        consentGiven=bool(contribution['consent_given_at']))
            state = 'RECOVERY_REQUIRED' if workflow['review_required'] else purchase['state']
            return dict(groupID=group_id, hasBooking=True, purchaseID=purchase['id'], state=state,
                offerID=offer['id'], title=offer['title'], domain=offer['domain'], totalCents=purchase['total_cents'],
                totalValue=money(purchase['total_cents']), currency=purchase['currency'], frozenAt=purchase['frozen_at'],
                holdDeadline=purchase['hold_deadline'], policy=purchase['policy'], isOrganizer=group['organizer_id'] == participant_id,
                myShare=own, rosterProgress=progress, error=workflow['error'], cancelRequested=bool(workflow['cancel_requested']),
                operationInProgress=workflow['lease_until'] > time.time(),
                recoveryRequired=state in ('RECOVERY_REQUIRED', 'CANCELLING'),
                providerEvidence='sandbox', inventorySource='controlled_local_catalog')

    def give_consent(self, participant_id, group_id):
        from .lease import claim_booking
        purchase = self.payments.purchase_for(participant_id, group_id)
        with claim_booking(self.store, purchase['id']) as lease:
            with lease.write() as connection:
                current = latest_purchase(connection, group_id)
                if current['state'] != 'AWAITING_AUTHORIZATIONS' or current['hold_deadline'] <= time.time():
                    raise BookingError('BOOKING_NOT_ACCEPTING_CONSENT')
                contribution = connection.execute(select(purchase_contributions).where(
                    purchase_contributions.c.purchase_id == purchase['id'],
                    purchase_contributions.c.participant_id == participant_id)).mappings().one()
                if not contribution['consent_given_at']:
                    connection.execute(update(purchase_contributions).where(purchase_contributions.c.id == contribution['id']).values(
                        state='ACCEPTED', consent_given_at=time.time()))
        return self.view(participant_id, group_id)

    def get_my_ticket(self, participant_id, group_id):
        with self.store.engine.connect() as connection:
            member_group(connection, participant_id, group_id)
            purchase = latest_purchase(connection, group_id)
            if not purchase or purchase['state'] != 'CONFIRMED':
                raise BookingError('NO_CONFIRMED_BOOKING', 404)
            workflow = connection.execute(select(group_workflows).where(group_workflows.c.purchase_id == purchase['id'])).mappings().one()
            if workflow['review_required']:
                raise BookingError('LEGACY_PURCHASE_REQUIRES_REVIEW')
            ticket = connection.execute(select(group_tickets).where(group_tickets.c.purchase_id == purchase['id'],
                group_tickets.c.participant_id == participant_id)).mappings().first()
            if not ticket:
                raise BookingError('TICKET_NOT_FOUND', 404)
            contribution = connection.execute(select(purchase_contributions).where(
                purchase_contributions.c.id == ticket['contribution_id'])).mappings().one()
            if contribution['state'] != 'CAPTURED':
                raise BookingError('PAYMENT_NOT_COMPLETED', 403)
            offer = connection.execute(select(catalog_offers).where(catalog_offers.c.id == purchase['offer_id'])).mappings().one()
            label = connection.execute(select(catalog_resources.c.label).where(catalog_resources.c.id == ticket['resource_id'])).scalar()
            return dict(ticketID=ticket['id'], ticketCode=ticket['ticket_code'], participantID=participant_id,
                alias=contribution['alias'], title=offer['title'], domain=offer['domain'], scheduleTime=offer['schedule_time'],
                assignedResource=label, shareCents=contribution['share_cents'], shareValue=money(contribution['share_cents']),
                currency=purchase['currency'], issuedAt=ticket['issued_at'], captureID=contribution['capture_id'],
                policy=purchase['policy'], inventorySource='controlled_local_catalog')

    def submit_preference(self, *args, **kwargs):
        return self.planning.submit_preference(*args, **kwargs)

    def confirm_preference(self, *args, **kwargs):
        return self.planning.confirm_preference(*args, **kwargs)

    def get_group_plan(self, *args, **kwargs):
        return self.planning.get_group_plan(*args, **kwargs)

    def initiate_contribution_order(self, *args):
        return self.payments.initiate(*args)

    def authorize_contribution(self, *args):
        return self.payments.authorize(*args)

    def reconcile_contribution(self, *args):
        return self.payments.reconcile(*args)

    def finalize_booking(self, *args):
        return self.payments.finalize(*args)

    def void_booking(self, *args):
        return self.payments.cancel(*args)

