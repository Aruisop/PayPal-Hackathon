"""Persistent invitation and workshop selection around independent bookings."""
import secrets
import time
from datetime import datetime, timezone

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from storage import bookings, group_memberships, identifier, workshop_groups, workshops


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
                workshop_id=None, created_at=now))
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
                existing = connection.execute(select(group_memberships.c.id).where(
                    group_memberships.c.group_id == group_id,
                    group_memberships.c.participant_id == participant_id)).scalar()
                if not existing:
                    # Enforce F03: Joining closes at roster freeze
                    try:
                        from storage import shared_purchases
                        frozen = connection.execute(select(shared_purchases.c.id).where(
                            shared_purchases.c.group_id == group_id,
                            shared_purchases.c.frozen_at.is_not(None),
                            shared_purchases.c.state.in_(['AWAITING_AUTHORIZATIONS', 'FINALIZING', 'CONFIRMED'])
                        )).scalar()
                        if frozen:
                            raise GroupError('ROSTER_FROZEN', 409)
                    except GroupError:
                        raise
                    except Exception:
                        pass
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
        own_booking = self.checkout.view(participant_id, booking_id) if booking_id else None
        organizer = group['organizer_id'] == participant_id
        result = dict(id=group_id, name=group['name'], role='organizer' if organizer else 'member',
            memberCount=count, workshopID=group['workshop_id'], myBooking=own_booking)
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
