"""Private, read-only counterfactual plans checked against every confirmed member."""
import copy
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.planning.interpreter import AIError, DeterministicCatalogMatcher, validate_constraints
from app.planning.service import Planning
from app.shared.storage import group_member_preferences, group_memberships, money, shared_purchases


class PlanRescue:
    def __init__(self, store):
        self.store = store
        self.planning = Planning(store)

    def suggest(self, participant_id, group_id, domain='movie'):
        if domain not in ('movie', 'excursion'):
            raise AIError('INVALID_DOMAIN')
        with self.store.engine.connect() as connection:
            self.planning._member(connection, participant_id, group_id)
            frozen = connection.execute(select(shared_purchases.c.id).where(
                shared_purchases.c.group_id == group_id,
                shared_purchases.c.state.not_in(('CANCELLED', 'EXPIRED')))).first()
            if frozen:
                raise AIError('ROSTER_ALREADY_FROZEN', 409)
            members = connection.execute(select(group_memberships.c.participant_id).where(
                group_memberships.c.group_id == group_id).order_by(
                group_memberships.c.joined_at, group_memberships.c.id)).scalars().all()
            base = dict(scope='private_counterfactual', engine='verified_rules', saved=False,
                        requiresConfirmation=True, proposals=[], memberCount=len(members))
            if len(members) < 2:
                return dict(base, status='needs_members', summary='Invite another person first. Your exact excursion share depends on the roster.')
            if len(members) > 4:
                raise AIError('GROUP_SIZE_UNSUPPORTED')
            rows = {r['participant_id']: r for r in connection.execute(select(group_member_preferences).where(
                group_member_preferences.c.group_id == group_id)).mappings()}
            if any(pid not in rows or not rows[pid]['is_confirmed'] for pid in members):
                return dict(base, status='needs_confirmation', summary='Everyone must confirm their own preferences before a group compromise can be verified.')
            constraints = [validate_constraints(json.loads(rows[pid]['confirmed_constraints_json'])) for pid in members]
            offers = self.planning._offers(connection, domain)
        # All computation is local, after the read connection is closed. No model
        # gets other members' raw preferences, aliases, budgets or payment IDs.
        own_index = members.index(participant_id)
        own = constraints[own_index]
        matcher = DeterministicCatalogMatcher()
        baseline = matcher.match(constraints, offers, len(members))['matches']
        proposals = []
        for offer in offers:
            total = offer['priceMinor'] * len(members) if domain == 'movie' else offer['priceMinor']
            share = total // len(members) + int(own_index < total % len(members))
            proposed, changes = self._adjust(own, offer, share)
            edited = copy.deepcopy(constraints)
            edited[own_index] = proposed
            if not matcher.match(edited, [offer], len(members))['matches']:
                continue
            proposals.append(dict(id=offer['id'], title=offer['title'], domain=domain,
                scheduleTime=offer['scheduleTime'], description=' '.join([offer['title'], domain, json.dumps(offer['meta'])]),
                localSchedule=datetime.fromisoformat(offer['scheduleTime']).astimezone(ZoneInfo(own['timezone'])).isoformat(),
                ownShareCents=share, ownShareValue=money(share), totalCents=total, totalValue=money(total), currency='USD',
                changes=changes, constraints=proposed, changeCount=len(changes),
                budgetIncreaseCents=max(0, share - own['budget_cents']) if own['budget_cents'] is not None else 0,
                fitsNow=not changes))
        proposals.sort(key=lambda p: (p['changeCount'], p['budgetIncreaseCents'], p['ownShareCents'], p['scheduleTime'], p['id']))
        summary = ('These options already fit every confirmed member. Compare the experience and exact shares.' if baseline else
                   'These small edits to your own preferences would unlock an option while keeping everyone else’s confirmed constraints unchanged.')
        if not proposals:
            summary = 'Changing only your preferences cannot unlock an available option. Discuss another plan with the group; nobody else’s private limits are shown here.'
        return dict(base, status='options' if proposals else 'blocked_elsewhere', summary=summary,
                    baselineMatchCount=len(baseline), proposals=proposals[:5])

    @staticmethod
    def _adjust(own, offer, share):
        proposed, changes = copy.deepcopy(own), []
        def change(field, before, after, label):
            changes.append(dict(field=field, before=before, after=after, label=label))
        if own['budget_cents'] is not None and share > own['budget_cents']:
            proposed['budget_cents'] = share
            change('budget_cents', own['budget_cents'], share,
                   f'Raise your ceiling from ${money(own["budget_cents"])} to ${money(share)} USD (+${money(share-own["budget_cents"])}).')
        local = datetime.fromisoformat(offer['scheduleTime']).astimezone(ZoneInfo(own['timezone']))
        day, date, start = local.strftime('%A').lower(), local.date().isoformat(), local.strftime('%H:%M')
        if own['dates'] and date not in own['dates']:
            proposed['dates'] = sorted(set(own['dates'] + [date]))
            change('dates', own['dates'], proposed['dates'], f'Also allow {date} in your timezone.')
        if own['preferred_days'] and day not in own['preferred_days']:
            proposed['preferred_days'] = sorted(set(own['preferred_days'] + [day]))
            change('preferred_days', own['preferred_days'], proposed['preferred_days'], f'Also allow {day.title()}.')
        window = proposed['time_window']
        for key, outside in [('earliest', start < window.get('earliest', '00:00')), ('latest', start > window.get('latest', '23:59'))]:
            if key in window and outside:
                before = window[key]; window[key] = start
                change('time_window.' + key, before, start, f'Change your {key} start from {before} to {start}.')
        end = local + timedelta(minutes=offer['meta'].get('runtime_min', 120))
        finish = window.get('finish_before')
        if finish and (end.date() != local.date() or end.strftime('%H:%M') > finish):
            if end.date() != local.date():
                del window['finish_before']
                change('time_window.finish_before', finish, None, f'Remove your finish-before limit for this option; it ends {end.strftime("%Y-%m-%d %H:%M")} locally.')
            else:
                window['finish_before'] = end.strftime('%H:%M')
                change('time_window.finish_before', finish, window['finish_before'], f'Allow finishing at {window["finish_before"]} instead of {finish}.')
        return validate_constraints(proposed), changes

