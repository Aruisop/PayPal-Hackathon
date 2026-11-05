"""Persistent member chat and coarse coordination; no payment or model actions."""
import hashlib
import json
import time
from sqlalchemy import and_, insert, or_, select

from app.planning.interpreter import AIError
from .journey import journey
from app.shared.storage import (group_member_preferences, group_member_profiles, group_memberships,
                     group_workflows, identifier, room_messages, shared_purchases, workshop_groups)


class Room:
    def __init__(self, store):
        self.store = store

    def _context(self, connection, participant_id, group_id):
        group = connection.execute(select(workshop_groups).join(group_memberships,
            group_memberships.c.group_id == workshop_groups.c.id).where(
            workshop_groups.c.id == group_id,
            group_memberships.c.participant_id == participant_id)).mappings().first()
        if not group:
            raise AIError('GROUP_NOT_FOUND', 404)
        members = connection.execute(select(group_memberships.c.participant_id).where(
            group_memberships.c.group_id == group_id).order_by(
            group_memberships.c.joined_at, group_memberships.c.id)).scalars().all()
        profiles = {r['participant_id']: r for r in connection.execute(select(group_member_profiles).where(
            group_member_profiles.c.group_id == group_id)).mappings()}
        aliases = {pid: profiles[pid]['alias'] if pid in profiles and
                   (pid == participant_id or profiles[pid]['consent_coarse_progress']) else f'Member {i + 1}'
                   for i, pid in enumerate(members)}
        return group, members, profiles, aliases

    def _message(self, row, participant_id, aliases):
        return dict(id=row['id'], participantID=row['participant_id'],
                    alias=aliases.get(row['participant_id'], 'Former member'), text=row['text'],
                    createdAt=row['created_at'], isSelf=row['participant_id'] == participant_id)

    def post_message(self, participant_id, group_id, text):
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > 1000 or '\x00' in text:
            raise AIError('MESSAGE_TEXT_REQUIRED')
        with self.store.engine.begin() as connection:
            _, _, _, aliases = self._context(connection, participant_id, group_id)
            row = dict(id=identifier(), group_id=group_id, participant_id=participant_id,
                       text=text.strip(), created_at=time.time())
            connection.execute(insert(room_messages).values(**row))
        return self._message(row, participant_id, aliases)

    def view(self, participant_id, group_id, after=None):
        with self.store.engine.connect() as connection:
            group, members, profiles, aliases = self._context(connection, participant_id, group_id)
            query = select(room_messages).where(room_messages.c.group_id == group_id)
            if after is not None:
                if not isinstance(after, str) or not 1 <= len(after) <= 40:
                    raise AIError('INVALID_MESSAGE_CURSOR')
                cursor = connection.execute(select(room_messages).where(
                    room_messages.c.group_id == group_id, room_messages.c.id == after)).mappings().first()
                if not cursor:
                    raise AIError('INVALID_MESSAGE_CURSOR')
                query = query.where(or_(room_messages.c.created_at > cursor['created_at'], and_(
                    room_messages.c.created_at == cursor['created_at'], room_messages.c.id > cursor['id'])))
            rows = connection.execute(query.order_by(room_messages.c.created_at.desc(),
                room_messages.c.id.desc()).limit(51)).mappings().all()
            preferences = connection.execute(select(group_member_preferences.c.participant_id,
                group_member_preferences.c.updated_at, group_member_preferences.c.is_confirmed).where(
                group_member_preferences.c.group_id == group_id).order_by(group_member_preferences.c.participant_id)).all()
            confirmed = {row.participant_id for row in preferences if row.is_confirmed}
            planning_version = hashlib.sha256(json.dumps([tuple(row) for row in preferences]).encode()).hexdigest()
            confirmed.intersection_update(members)
            purchase = connection.execute(select(shared_purchases).where(
                shared_purchases.c.group_id == group_id).order_by(
                shared_purchases.c.created_at.desc(), shared_purchases.c.id).limit(1)).mappings().first()
            phase = 'invite' if len(members) < 2 else ('ready_to_select' if len(confirmed) == len(members) else 'planning')
            if purchase and purchase['state'] not in ('CANCELLED', 'EXPIRED'):
                phase = purchase['state'].lower()
                workflow = connection.execute(select(group_workflows.c.review_required).where(
                    group_workflows.c.purchase_id == purchase['id'])).scalar()
                if workflow:
                    phase = 'recovery_required'
            actions = dict(invite='Copy the invite link and ask a friend to join in a separate browser profile.',
                           planning='Each member can privately review and confirm their preferences.',
                           ready_to_select='The organizer can review suitable options and select seats or places.',
                           awaiting_authorizations='Review your exact share and approve only your own PayPal hold.',
                           confirmed='Open your own private demonstration ticket.',
                           finalizing='Payment confirmation is being checked; keep the reservation intact.',
                           recovery_required='Review your own payment status and request a recheck.',
                           cancelling='Recovery is still being checked; a refund request is not a completed refund.')
            roster = [dict(participantID=pid, alias=aliases[pid], isOrganizer=pid == group['organizer_id'],
                           isMe=pid == participant_id, hasConfirmed=pid in confirmed)
                      for pid in members if pid == participant_id or
                      (pid in profiles and profiles[pid]['consent_coarse_progress'])]
            return dict(groupID=group_id, messages=[self._message(row, participant_id, aliases) for row in reversed(rows[:50])],
                        memberCount=len(members), confirmedCount=len(confirmed), phase=phase, roster=roster,
                        unconfirmedMembers=[aliases[pid] for pid in members if pid not in confirmed],
                        nextAction=actions.get(phase, 'Review the current booking status.'), truncated=len(rows) > 50,
                        planningVersion=planning_version,
                        journey=journey(phase, member_count=len(members), confirmed_count=len(confirmed),
                                        own_confirmed=participant_id in confirmed,
                                        organizer=participant_id == group['organizer_id']))

