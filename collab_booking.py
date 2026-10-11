import json
import secrets
import time
from datetime import datetime, timezone
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from ai_planner import AIError, DeterministicCatalogMatcher, GroupPlanExplainer, PreferenceInterpreter
from storage import (catalog_offers, catalog_resources, group_member_preferences,
                     group_member_profiles, group_memberships, identifier, money,
                     purchase_contributions, shared_purchases, split_equal_cents,
                     workshop_groups)


class BookingError(Exception):
    def __init__(self, issue, status=409):
        self.issue, self.status = issue, status


class CollabBooking:
    def __init__(self, store, origin):
        self.store = store
        self.origin = origin

    def _member_group(self, connection, participant_id, group_id):
        return connection.execute(select(workshop_groups).join(
            group_memberships, group_memberships.c.group_id == workshop_groups.c.id).where(
            workshop_groups.c.id == group_id,
            group_memberships.c.participant_id == participant_id)).mappings().first()

    def _get_active_purchase(self, connection, group_id):
        return connection.execute(select(shared_purchases).where(
            shared_purchases.c.group_id == group_id,
            shared_purchases.c.state.in_(['DRAFT', 'AWAITING_AUTHORIZATIONS', 'FINALIZING', 'CONFIRMED'])
        ).order_by(shared_purchases.c.created_at.desc())).mappings().first()

    def set_profile(self, participant_id, group_id, alias, consent=True):
        if not isinstance(alias, str) or not alias.strip() or len(alias.strip()) > 60:
            raise BookingError('INVALID_ALIAS', 400)
        clean_alias = alias.strip()
        with self.store.engine.begin() as connection:
            group = self._member_group(connection, participant_id, group_id)
            if not group:
                raise BookingError('GROUP_NOT_FOUND', 404)
            active = self._get_active_purchase(connection, group_id)
            if active and active['frozen_at']:
                raise BookingError('ROSTER_ALREADY_FROZEN', 409)
            existing = connection.execute(select(group_member_profiles.c.id).where(
                group_member_profiles.c.group_id == group_id,
                group_member_profiles.c.participant_id == participant_id)).scalar()
            now = time.time()
            if existing:
                connection.execute(update(group_member_profiles).where(
                    group_member_profiles.c.id == existing).values(
                    alias=clean_alias, consent_coarse_progress=1 if consent else 0, updated_at=now))
            else:
                connection.execute(insert(group_member_profiles).values(
                    id=identifier(), group_id=group_id, participant_id=participant_id,
                    alias=clean_alias, consent_coarse_progress=1 if consent else 0, updated_at=now))
        return dict(participantID=participant_id, alias=clean_alias)

    def quote(self, participant_id, group_id, offer_id, selected_resource_ids=None):
        with self.store.engine.connect() as connection:
            group = self._member_group(connection, participant_id, group_id)
            if not group:
                raise BookingError('GROUP_NOT_FOUND', 404)
            members = connection.execute(select(group_memberships.c.participant_id).where(
                group_memberships.c.group_id == group_id).order_by(group_memberships.c.joined_at)).scalars().all()
            if len(members) < 2 or len(members) > 4:
                raise BookingError('GROUP_SIZE_UNSUPPORTED', 400)
            offer = connection.execute(select(catalog_offers).where(catalog_offers.c.id == offer_id)).mappings().first()
            if not offer:
                raise BookingError('OFFER_NOT_FOUND', 404)

            # Check resources if provided
            if selected_resource_ids:
                if len(selected_resource_ids) != len(members):
                    raise BookingError('RESOURCE_COUNT_MISMATCH', 400)
                resources = connection.execute(select(catalog_resources).where(
                    catalog_resources.c.id.in_(selected_resource_ids),
                    catalog_resources.c.offer_id == offer_id)).mappings().all()
                if len(resources) != len(selected_resource_ids):
                    raise BookingError('INVALID_RESOURCES', 400)
                for r in resources:
                    if r['state'] != 'FREE':
                        raise BookingError('SEAT_UNAVAILABLE', 409)

            # Authoritative pricing calculation
            if offer['domain'] == 'movie':
                total_cents = offer['price_minor'] * len(members)
            else:
                total_cents = offer['price_minor']

            shares = split_equal_cents(total_cents, members)
            share_list = [{'participantID': pid, 'shareCents': cents, 'shareValue': money(cents)}
                          for pid, cents in shares.items()]

            return dict(
                offerID=offer['id'],
                domain=offer['domain'],
                title=offer['title'],
                merchantID=offer['merchant_id'],
                scheduleTime=offer['schedule_time'],
                totalCents=total_cents,
                totalValue=money(total_cents),
                currency=offer['currency'],
                memberCount=len(members),
                shares=share_list,
                roundingRule='Equal integer cent allocation: T // N cents each, with remainder distributed 1 cent each in roster order.',
                policy='all_or_nothing_refund'
            )

    def freeze(self, participant_id, group_id, offer_id, selected_resource_ids):
        if not selected_resource_ids or not isinstance(selected_resource_ids, list):
            raise BookingError('RESOURCES_REQUIRED', 400)
        with self.store.engine.begin() as connection:
            group = self._member_group(connection, participant_id, group_id)
            if not group:
                raise BookingError('GROUP_NOT_FOUND', 404)
            if group['organizer_id'] != participant_id:
                raise BookingError('ORGANIZER_REQUIRED', 403)
            active = self._get_active_purchase(connection, group_id)
            if active and active['frozen_at']:
                raise BookingError('ROSTER_ALREADY_FROZEN', 409)

            members = connection.execute(select(group_memberships.c.participant_id).where(
                group_memberships.c.group_id == group_id).order_by(group_memberships.c.joined_at)).scalars().all()
            if len(members) < 2 or len(members) > 4:
                raise BookingError('GROUP_SIZE_UNSUPPORTED', 400)
            if len(selected_resource_ids) != len(members):
                raise BookingError('RESOURCE_COUNT_MISMATCH', 400)

            offer = connection.execute(select(catalog_offers).where(catalog_offers.c.id == offer_id)).mappings().first()
            if not offer:
                raise BookingError('OFFER_NOT_FOUND', 404)

            # Fetch resources with lock verification
            resources = connection.execute(select(catalog_resources).where(
                catalog_resources.c.id.in_(selected_resource_ids),
                catalog_resources.c.offer_id == offer_id)).mappings().all()
            if len(resources) != len(selected_resource_ids):
                raise BookingError('INVALID_RESOURCES', 400)
            for r in resources:
                if r['state'] != 'FREE':
                    raise BookingError('SEAT_UNAVAILABLE', 409)

            # Authoritative pricing
            if offer['domain'] == 'movie':
                total_cents = offer['price_minor'] * len(members)
            else:
                total_cents = offer['price_minor']

            shares = split_equal_cents(total_cents, members)
            now = time.time()
            deadline = now + 900  # 15-minute server-owned hold deadline
            purchase_id = identifier()

            # Create shared purchase
            connection.execute(insert(shared_purchases).values(
                id=purchase_id, group_id=group_id, offer_id=offer_id,
                state='AWAITING_AUTHORIZATIONS', total_cents=total_cents, currency=offer['currency'],
                frozen_at=now, hold_deadline=deadline, policy='all_or_nothing_refund',
                fenced_claim_token=None, created_at=now))

            # Hold resources
            for rid in selected_resource_ids:
                connection.execute(update(catalog_resources).where(
                    catalog_resources.c.id == rid, catalog_resources.c.state == 'FREE').values(
                    state='HELD', held_by_purchase_id=purchase_id, held_until=deadline))

            # Fetch profiles for aliases
            profiles = dict(connection.execute(select(
                group_member_profiles.c.participant_id, group_member_profiles.c.alias).where(
                group_member_profiles.c.group_id == group_id)).all())

            # Create contributions bound to members in stable order
            for i, pid in enumerate(members):
                alias = profiles.get(pid, f'Member {i + 1}')
                assigned_res = selected_resource_ids[i]
                connection.execute(insert(purchase_contributions).values(
                    id=identifier(), purchase_id=purchase_id, participant_id=pid,
                    alias=alias, share_cents=shares[pid], assigned_resource_id=assigned_res,
                    state='PENDING_CONSENT', consent_given_at=None,
                    order_id=None, authorization_id=None, capture_id=None, created_at=now))

        return self.view(participant_id, group_id)

    def view(self, participant_id, group_id):
        with self.store.engine.connect() as connection:
            group = self._member_group(connection, participant_id, group_id)
            if not group:
                raise BookingError('GROUP_NOT_FOUND', 404)
            active = self._get_active_purchase(connection, group_id)
            if not active:
                return dict(groupID=group_id, hasBooking=False)

            offer = connection.execute(select(catalog_offers).where(
                catalog_offers.c.id == active['offer_id'])).mappings().first()

            all_contribs = connection.execute(select(purchase_contributions).where(
                purchase_contributions.c.purchase_id == active['id'])).mappings().all()

            # Coarse progress safe for all members
            coarse_progress = []
            own_contribution = None
            for c in all_contribs:
                coarse_progress.append(dict(
                    alias=c['alias'],
                    state=c['state'],
                    hasConsented=bool(c['consent_given_at']),
                    hasAuthorized=bool(c['authorization_id'])
                ))
                if c['participant_id'] == participant_id:
                    res_label = None
                    if c['assigned_resource_id']:
                        res_label = connection.execute(select(catalog_resources.c.label).where(
                            catalog_resources.c.id == c['assigned_resource_id'])).scalar()
                    own_contribution = dict(
                        contributionID=c['id'],
                        alias=c['alias'],
                        shareCents=c['share_cents'],
                        shareValue=money(c['share_cents']),
                        assignedResource=res_label,
                        state=c['state'],
                        consentGiven=bool(c['consent_given_at'])
                    )

            is_organizer = group['organizer_id'] == participant_id
            return dict(
                groupID=group_id,
                hasBooking=True,
                purchaseID=active['id'],
                state=active['state'],
                offerID=offer['id'],
                title=offer['title'],
                domain=offer['domain'],
                totalCents=active['total_cents'],
                totalValue=money(active['total_cents']),
                currency=active['currency'],
                frozenAt=active['frozen_at'],
                holdDeadline=active['hold_deadline'],
                policy=active['policy'],
                isOrganizer=is_organizer,
                myShare=own_contribution,
                rosterProgress=coarse_progress
            )

    def give_consent(self, participant_id, group_id):
        with self.store.engine.begin() as connection:
            group = self._member_group(connection, participant_id, group_id)
            if not group:
                raise BookingError('GROUP_NOT_FOUND', 404)
            active = self._get_active_purchase(connection, group_id)
            if not active or active['state'] != 'AWAITING_AUTHORIZATIONS':
                raise BookingError('NO_ACTIVE_BOOKING', 400)
            now = time.time()
            res = connection.execute(update(purchase_contributions).where(
                purchase_contributions.c.purchase_id == active['id'],
                purchase_contributions.c.participant_id == participant_id).values(
                state='ACCEPTED', consent_given_at=now))
            if res.rowcount != 1:
                raise BookingError('CONTRIBUTION_NOT_FOUND', 404)
        return self.view(participant_id, group_id)

    def submit_preference(self, participant_id, group_id, raw_text, user_tz='UTC', reference_date=None):
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise BookingError('PREFERENCE_TEXT_REQUIRED', 400)
        clean_text = raw_text.strip()[:1000]

        with self.store.engine.connect() as connection:
            group = self._member_group(connection, participant_id, group_id)
            if not group:
                raise BookingError('GROUP_NOT_FOUND', 404)
            active = self._get_active_purchase(connection, group_id)
            if active and active['frozen_at']:
                raise BookingError('ROSTER_ALREADY_FROZEN', 409)

        interpreter = PreferenceInterpreter()
        interpreted = interpreter.interpret(clean_text, user_tz=user_tz, reference_date=reference_date)

        now = time.time()
        with self.store.engine.begin() as connection:
            active = self._get_active_purchase(connection, group_id)
            if active and active['frozen_at']:
                raise BookingError('ROSTER_ALREADY_FROZEN', 409)

            existing = connection.execute(select(group_member_preferences.c.id).where(
                group_member_preferences.c.group_id == group_id,
                group_member_preferences.c.participant_id == participant_id)).scalar()

            if existing:
                connection.execute(update(group_member_preferences).where(
                    group_member_preferences.c.id == existing).values(
                    raw_text=clean_text,
                    interpreted_json=json.dumps(interpreted),
                    confirmed_constraints_json=None,
                    is_confirmed=0,
                    updated_at=now
                ))
            else:
                connection.execute(insert(group_member_preferences).values(
                    id=identifier(),
                    group_id=group_id,
                    participant_id=participant_id,
                    raw_text=clean_text,
                    interpreted_json=json.dumps(interpreted),
                    confirmed_constraints_json=None,
                    is_confirmed=0,
                    updated_at=now
                ))

        return {
            'groupID': group_id,
            'participantID': participant_id,
            'status': 'INTERPRETED',
            'isConfirmed': False,
            'interpretation': interpreted
        }

    def confirm_preference(self, participant_id, group_id, confirmed_constraints):
        if not isinstance(confirmed_constraints, dict):
            raise BookingError('CONSTRAINTS_REQUIRED', 400)

        with self.store.engine.begin() as connection:
            group = self._member_group(connection, participant_id, group_id)
            if not group:
                raise BookingError('GROUP_NOT_FOUND', 404)
            active = self._get_active_purchase(connection, group_id)
            if active and active['frozen_at']:
                raise BookingError('ROSTER_ALREADY_FROZEN', 409)

            pref = connection.execute(select(group_member_preferences).where(
                group_member_preferences.c.group_id == group_id,
                group_member_preferences.c.participant_id == participant_id)).mappings().first()
            if not pref:
                raise BookingError('PREFERENCE_NOT_FOUND', 404)

            now = time.time()
            connection.execute(update(group_member_preferences).where(
                group_member_preferences.c.id == pref['id']).values(
                confirmed_constraints_json=json.dumps(confirmed_constraints),
                is_confirmed=1,
                updated_at=now
            ))

        return {
            'groupID': group_id,
            'participantID': participant_id,
            'status': 'CONFIRMED',
            'isConfirmed': True,
            'confirmedConstraints': confirmed_constraints
        }

    def get_group_plan(self, participant_id, group_id, domain='movie'):
        with self.store.engine.connect() as connection:
            group = self._member_group(connection, participant_id, group_id)
            if not group:
                raise BookingError('GROUP_NOT_FOUND', 404)

            members = connection.execute(select(group_memberships.c.participant_id).where(
                group_memberships.c.group_id == group_id).order_by(group_memberships.c.joined_at)).scalars().all()
            if len(members) < 2 or len(members) > 4:
                raise BookingError('GROUP_SIZE_UNSUPPORTED', 400)

            profiles = dict(connection.execute(select(
                group_member_profiles.c.participant_id, group_member_profiles.c.alias).where(
                group_member_profiles.c.group_id == group_id)).all())

            # Load preferences
            prefs = connection.execute(select(group_member_preferences).where(
                group_member_preferences.c.group_id == group_id)).mappings().all()
            pref_by_pid = {p['participant_id']: p for p in prefs}

            member_constraints = []
            unconfirmed_members = []
            for i, pid in enumerate(members):
                alias = profiles.get(pid, f'Member {i + 1}')
                p = pref_by_pid.get(pid)
                if p and p['is_confirmed'] and p['confirmed_constraints_json']:
                    c = json.loads(p['confirmed_constraints_json'])
                    c['participant_id'] = pid
                    c['alias'] = alias
                    c['is_confirmed'] = True
                    member_constraints.append(c)
                else:
                    unconfirmed_members.append(alias)
                    tentative = json.loads(p['interpreted_json']) if p else {}
                    tentative['participant_id'] = pid
                    tentative['alias'] = alias
                    tentative['is_confirmed'] = False
                    member_constraints.append(tentative)

            # Query catalog offers for this domain
            raw_offers = connection.execute(select(catalog_offers).where(
                catalog_offers.c.domain == domain)).mappings().all()

            offers = []
            for ro in raw_offers:
                res_rows = connection.execute(select(catalog_resources).where(
                    catalog_resources.c.offer_id == ro['id']).order_by(
                    catalog_resources.c.label)).mappings().all()
                resources = [dict(id=r['id'], label=r['label'], state=r['state']) for r in res_rows]
                meta = json.loads(ro['meta_json']) if ro.get('meta_json') else {}
                offers.append(dict(
                    id=ro['id'],
                    domain=ro['domain'],
                    title=ro['title'],
                    merchantID=ro['merchant_id'],
                    scheduleTime=ro['schedule_time'],
                    priceMinor=ro['price_minor'],
                    value=money(ro['price_minor']),
                    currency=ro['currency'],
                    meta=meta,
                    resources=resources
                ))

            matcher = DeterministicCatalogMatcher()
            matched_res = matcher.match(member_constraints, offers, group_size=len(members))
            explainer = GroupPlanExplainer()
            explanation = explainer.explain(matched_res['matches'], matched_res['conflicts'], member_constraints)

            return {
                'groupID': group_id,
                'domain': domain,
                'groupSize': len(members),
                'memberCount': len(members),
                'confirmedCount': len(members) - len(unconfirmed_members),
                'unconfirmedMembers': unconfirmed_members,
                'allConfirmed': len(unconfirmed_members) == 0,
                'matches': matched_res['matches'],
                'conflicts': matched_res['conflicts'],
                'explanation': explanation
            }

