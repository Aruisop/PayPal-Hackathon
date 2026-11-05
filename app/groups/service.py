"""Persistent invitation and workshop selection around independent bookings."""
import secrets
import time
from datetime import datetime, timezone

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.shared.storage import (bookings, catalog_offers, catalog_resources, group_memberships,
                                identifier, workshop_groups, workshops)


class GroupError(Exception):
    def __init__(self, issue, status=409):
        self.issue, self.status = issue, status


class Groups:
    def __init__(self, store, checkout, origin):
        self.store, self.checkout, self.origin = store, checkout, origin

    def create(self, participant_id, name):
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
            raise GroupError('GROUP_NAME_REQUIRED', 400)
        group_id = identifier()
        now = time.time()
        with self.store.engine.begin() as connection:
            connection.execute(insert(workshop_groups).values(id=group_id, name=name.strip(),
                organizer_id=participant_id, invite_token=secrets.token_urlsafe(32),
                workshop_id=None, checkout_mode='planning', target_member_count=None,
                merchant_offer_id=None, created_at=now))
            connection.execute(insert(group_memberships).values(id=identifier(), group_id=group_id,
                participant_id=participant_id, joined_at=now))
        return self.view(participant_id, group_id)

    def create_merchant_checkout(self, participant_id, offer_id, payer_count):
        """Start a compact checkout around a trusted catalog offer only."""
        if not isinstance(offer_id, str) or type(payer_count) is not int or not 1 <= payer_count <= 4:
            raise GroupError('INVALID_MERCHANT_CHECKOUT', 400)
        group_id, now = identifier(), time.time()
        with self.store.engine.begin() as connection:
            offer = connection.execute(select(catalog_offers).where(catalog_offers.c.id == offer_id)).mappings().first()
            if not offer or offer['currency'] != 'USD' or datetime.fromisoformat(offer['schedule_time']).astimezone(timezone.utc) <= datetime.now(timezone.utc):
                raise GroupError('MERCHANT_OFFER_UNAVAILABLE', 409)
            available = connection.execute(select(func.count()).select_from(catalog_resources).where(
                catalog_resources.c.offer_id == offer_id, catalog_resources.c.state == 'FREE')).scalar_one()
            if available < payer_count:
                raise GroupError('MERCHANT_INVENTORY_UNAVAILABLE', 409)
            connection.execute(insert(workshop_groups).values(id=group_id, name=f"Checkout · {offer['title']}",
                organizer_id=participant_id, invite_token=secrets.token_urlsafe(32), workshop_id=None,
                checkout_mode='merchant', target_member_count=payer_count, merchant_offer_id=offer_id, created_at=now))
            connection.execute(insert(group_memberships).values(id=identifier(), group_id=group_id,
                participant_id=participant_id, joined_at=now))
        return self.view(participant_id, group_id)

    def join(self, participant_id, invite_token):
        if not isinstance(invite_token, str) or len(invite_token) > 64 or not invite_token:
            raise GroupError('INVITE_NOT_FOUND', 404)
        try:
            with self.store.engine.begin() as connection:
                group_id = connection.execute(select(workshop_groups.c.id).where(
                    workshop_groups.c.invite_token == invite_token)).scalar()
                if not group_id:
                    raise GroupError('INVITE_NOT_FOUND', 404)
                connection.execute(update(workshop_groups).where(workshop_groups.c.id == group_id).values(id=group_id))
                existing = connection.execute(select(group_memberships.c.id).where(
                    group_memberships.c.group_id == group_id,
                    group_memberships.c.participant_id == participant_id)).scalar()
                if not existing:
                    from app.shared.storage import shared_purchases
                    frozen = connection.execute(select(shared_purchases.c.id).where(
                        shared_purchases.c.group_id == group_id,
                        shared_purchases.c.frozen_at.is_not(None),
                        shared_purchases.c.state.in_(['AWAITING_AUTHORIZATIONS', 'FINALIZING',
                            'CONFIRMED', 'RECOVERY_REQUIRED', 'CANCELLING'])
                    )).scalar()
                    if frozen:
                        raise GroupError('ROSTER_FROZEN', 409)
                    count = connection.execute(select(func.count()).select_from(group_memberships).where(
                        group_memberships.c.group_id == group_id)).scalar_one()
                    target = connection.execute(select(workshop_groups.c.target_member_count).where(
                        workshop_groups.c.id == group_id)).scalar()
                    if count >= (target or 4):
                        raise GroupError('GROUP_MAX_CAPACITY', 409)
                    connection.execute(insert(group_memberships).values(id=identifier(), group_id=group_id,
                        participant_id=participant_id, joined_at=time.time()))
        except IntegrityError:
            # The participant joined in another concurrent request.
            with self.store.engine.connect() as connection:
                group_id = connection.execute(select(workshop_groups.c.id).where(
                    workshop_groups.c.invite_token == invite_token)).scalar()
                if not group_id or not connection.execute(select(group_memberships.c.id).where(
                    group_memberships.c.group_id == group_id,
                    group_memberships.c.participant_id == participant_id)).scalar():
                    raise
        return self.view(participant_id, group_id)

    def _member_group(self, connection, participant_id, group_id):
        return connection.execute(select(workshop_groups).join(group_memberships,
            group_memberships.c.group_id == workshop_groups.c.id).where(
            workshop_groups.c.id == group_id,
            group_memberships.c.participant_id == participant_id)).mappings().first()

    def view(self, participant_id, group_id):
        with self.store.engine.connect() as connection:
            group = self._member_group(connection, participant_id, group_id)
            if not group:
                raise GroupError('GROUP_NOT_FOUND', 404)
            count = connection.execute(select(func.count()).select_from(group_memberships).where(
                group_memberships.c.group_id == group_id)).scalar_one()
            booking_id = None
            if group['workshop_id']:
                booking_id = connection.execute(select(bookings.c.id).where(
                    bookings.c.participant_id == participant_id,
                    bookings.c.workshop_id == group['workshop_id'])).scalar()
            from app.shared.storage import group_member_profiles
            member_rows = connection.execute(select(
                group_memberships.c.participant_id, group_member_profiles.c.alias,
                group_member_profiles.c.consent_coarse_progress
            ).select_from(group_memberships.outerjoin(group_member_profiles,
                (group_member_profiles.c.group_id == group_memberships.c.group_id) &
                (group_member_profiles.c.participant_id == group_memberships.c.participant_id)
            )).where(group_memberships.c.group_id == group_id).order_by(
                group_memberships.c.joined_at, group_memberships.c.id)).mappings().all()
            members_data = [dict(participantID=row['participant_id'],
                alias=(row['alias'] if row['participant_id'] == participant_id or row['consent_coarse_progress'] else None)
                    or ('Organizer' if row['participant_id'] == group['organizer_id'] else f'Member {index + 1}'),
                isOrganizer=row['participant_id'] == group['organizer_id']) for index, row in enumerate(member_rows)]
            profile = next(row for row in member_rows if row['participant_id'] == participant_id)
            merchant_checkout = None
            if group['checkout_mode'] == 'merchant':
                offer = connection.execute(select(catalog_offers).where(
                    catalog_offers.c.id == group['merchant_offer_id'])).mappings().one()
                merchant_total = offer['price_minor'] * group['target_member_count'] if offer['domain'] == 'movie' else offer['price_minor']
                merchant_checkout = dict(offerID=offer['id'], title=offer['title'],
                    merchantID=offer['merchant_id'], totalCents=merchant_total, currency=offer['currency'],
                    targetMemberCount=group['target_member_count'], readyToFreeze=count == group['target_member_count'])
        own_booking = self.checkout.view(participant_id, booking_id) if booking_id else None
        organizer = group['organizer_id'] == participant_id
        result = dict(id=group_id, name=group['name'], role='organizer' if organizer else 'member',
            memberCount=count, workshopID=group['workshop_id'], myBooking=own_booking,
            members=members_data, myProfile=dict(alias=profile['alias'] or '',
                shareProgress=bool(profile['consent_coarse_progress'])))
        if merchant_checkout:
            result['merchantCheckout'] = merchant_checkout
        if organizer:
            result['inviteURL'] = f'{self.origin}/?invite={group["invite_token"]}'
        return result

    def list(self, participant_id):
        with self.store.engine.connect() as connection:
            ids = connection.execute(select(group_memberships.c.group_id).where(
                group_memberships.c.participant_id == participant_id).order_by(
                group_memberships.c.joined_at)).scalars().all()
        return [self.view(participant_id, group_id) for group_id in ids]

    def select_workshop(self, participant_id, group_id, workshop_id):
        if not isinstance(workshop_id, str):
            raise GroupError('WORKSHOP_REQUIRED', 400)
        with self.store.engine.begin() as connection:
            group = self._member_group(connection, participant_id, group_id)
            if not group:
                raise GroupError('GROUP_NOT_FOUND', 404)
            if group['organizer_id'] != participant_id:
                raise GroupError('ORGANIZER_REQUIRED', 403)
            if group['workshop_id'] and group['workshop_id'] != workshop_id:
                raise GroupError('GROUP_SELECTION_LOCKED')
            if not group['workshop_id']:
                workshop = connection.execute(select(workshops.c.starts_at).where(
                    workshops.c.id == workshop_id)).scalar()
                if not workshop:
                    raise GroupError('WORKSHOP_NOT_FOUND', 404)
                if datetime.fromisoformat(workshop) <= datetime.now(timezone.utc):
                    raise GroupError('WORKSHOP_ALREADY_STARTED')
                chosen = connection.execute(update(workshop_groups).where(workshop_groups.c.id == group_id,
                    workshop_groups.c.workshop_id.is_(None)).values(workshop_id=workshop_id))
                if chosen.rowcount != 1:
                    raise GroupError('GROUP_SELECTION_LOCKED')
        return self.view(participant_id, group_id)

