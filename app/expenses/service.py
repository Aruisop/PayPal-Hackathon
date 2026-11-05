"""Persistent friends, splits and subscriptions; settlement is a manual note only."""
import time

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.shared.storage import (expense_friends, expense_profiles, expense_share_contacts, expense_shares, expense_splits,
                                expense_split_payees, expense_subscription_details,
                                expense_subscription_participants, expense_subscriptions,
                                group_memberships, identifier, split_equal_cents, workshop_groups)

CATEGORIES = ('food', 'travel', 'rent', 'entertainment', 'shopping', 'other')
MAX_TOTAL_MINOR = 100_000_000  # $1,000,000.00; informal personal ledger, not a payment limit
ALL = object()  # sentinel: "no group filter", distinct from an explicit None (ungrouped only)


class ExpenseError(Exception):
    def __init__(self, issue, status=400):
        self.issue, self.status = issue, status
        super().__init__(issue)


def _name(value, *, field='name', max_len=80, required=True):
    if value is None and not required:
        return ''
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > max_len:
        raise ExpenseError(f'INVALID_{field.upper()}')
    return value.strip()


def _amount_minor(value):
    if type(value) is bool or type(value) not in (int,) or not 0 <= value <= MAX_TOTAL_MINOR:
        raise ExpenseError('INVALID_AMOUNT_MINOR')
    return value


class Expenses:
    def __init__(self, store):
        self.store = store

    # ---------------------------------------------------------------- profile
    def get_profile(self, participant_id):
        with self.store.engine.connect() as connection:
            row = connection.execute(select(expense_profiles).where(
                expense_profiles.c.participant_id == participant_id)).mappings().first()
        return dict(displayName=row['display_name'], upiID=row['upi_id']) if row else dict(displayName='', upiID='')

    def set_profile(self, participant_id, display_name, upi_id):
        display_name = _name(display_name, field='display_name', required=False) if display_name else ''
        upi_id = _name(upi_id, field='upi_id', max_len=80, required=False) if upi_id else ''
        now = time.time()
        with self.store.engine.begin() as connection:
            existing = connection.execute(select(expense_profiles.c.participant_id).where(
                expense_profiles.c.participant_id == participant_id)).first()
            if existing:
                connection.execute(update(expense_profiles).where(
                    expense_profiles.c.participant_id == participant_id).values(
                    display_name=display_name, upi_id=upi_id, updated_at=now))
            else:
                connection.execute(insert(expense_profiles).values(
                    participant_id=participant_id, display_name=display_name, upi_id=upi_id, updated_at=now))
        return self.get_profile(participant_id)

    # ---------------------------------------------------------------- friends
    def list_friends(self, participant_id):
        with self.store.engine.connect() as connection:
            rows = connection.execute(select(expense_friends).where(
                expense_friends.c.owner_id == participant_id).order_by(expense_friends.c.name)).mappings().all()
        return [dict(id=r['id'], name=r['name'], upiID=r['upi_id'], whatsapp=r['whatsapp']) for r in rows]

    def add_friend(self, participant_id, name, upi_id='', whatsapp=''):
        name = _name(name)
        upi_id = _name(upi_id, field='upi_id', required=False) if upi_id else ''
        whatsapp = _name(whatsapp, field='whatsapp', max_len=40, required=False) if whatsapp else ''
        friend_id = identifier()
        try:
            with self.store.engine.begin() as connection:
                connection.execute(insert(expense_friends).values(
                    id=friend_id, owner_id=participant_id, name=name, upi_id=upi_id,
                    whatsapp=whatsapp, created_at=time.time()))
        except IntegrityError:
            raise ExpenseError('FRIEND_NAME_ALREADY_USED', 409)
        return self.list_friends(participant_id)

    def remove_friend(self, participant_id, friend_id):
        with self.store.engine.begin() as connection:
            result = connection.execute(delete(expense_friends).where(
                expense_friends.c.id == friend_id, expense_friends.c.owner_id == participant_id))
            if result.rowcount == 0:
                raise ExpenseError('FRIEND_NOT_FOUND', 404)
        return self.list_friends(participant_id)

    # ------------------------------------------------------------- group tie-in
    def _assert_group_member(self, connection, participant_id, group_id):
        member = connection.execute(select(workshop_groups.c.id).join(
            group_memberships, group_memberships.c.group_id == workshop_groups.c.id).where(
            workshop_groups.c.id == group_id,
            group_memberships.c.participant_id == participant_id)).first()
        if not member:
            raise ExpenseError('GROUP_NOT_FOUND', 404)

    # --------------------------------------------------------------- splits
    def create_split(self, participant_id, title, category, currency, shares, *, group_id=None, source='manual',
                     receipt_meta=None, payee=None):
        title = _name(title, field='title', max_len=160)
        if category not in CATEGORIES:
            raise ExpenseError('INVALID_CATEGORY')
        if not isinstance(currency, str) or not currency.isalpha() or len(currency) != 3:
            raise ExpenseError('INVALID_CURRENCY')
        currency = currency.upper()
        if source not in ('manual', 'scan'):
            raise ExpenseError('INVALID_SOURCE')
        if not isinstance(shares, list) or not 1 <= len(shares) <= 50:
            raise ExpenseError('INVALID_SHARES')
        clean_shares, payer_count, seen_names, seen_friends = [], 0, set(), set()
        for share in shares:
            if not isinstance(share, dict):
                raise ExpenseError('INVALID_SHARES')
            name = _name(share.get('name'), field='share_name')
            lowered = name.lower()
            if lowered in seen_names:
                raise ExpenseError('DUPLICATE_SHARE_NAME')
            seen_names.add(lowered)
            amount_minor = _amount_minor(share.get('amountMinor'))
            is_payer = bool(share.get('isPayer'))
            friend_id = share.get('friendID')
            if friend_id is not None and (not isinstance(friend_id, str) or not friend_id or is_payer):
                raise ExpenseError('INVALID_FRIEND_REFERENCE')
            if friend_id in seen_friends:
                raise ExpenseError('DUPLICATE_FRIEND_REFERENCE')
            if friend_id:
                seen_friends.add(friend_id)
            payer_count += is_payer
            clean_shares.append(dict(name=name, amount_minor=amount_minor, is_payer=is_payer,
                                     friend_id=friend_id))
        if payer_count != 1:
            raise ExpenseError('EXACTLY_ONE_PAYER_REQUIRED')
        total_minor = sum(s['amount_minor'] for s in clean_shares)
        if not 0 < total_minor <= MAX_TOTAL_MINOR:
            raise ExpenseError('INVALID_TOTAL_MINOR')
        if payee is not None and not isinstance(payee, dict):
            raise ExpenseError('INVALID_PAYEE')
        payee = payee or {}
        host_name = _name(payee.get('hostName'), field='host_name', required=False) if payee.get('hostName') else ''
        upi_id = _name(payee.get('upiID'), field='upi_id', required=False) if payee.get('upiID') else ''
        paypal_email = _name(payee.get('paypalEmail'), field='paypal_email', max_len=160, required=False) if payee.get('paypalEmail') else ''
        if paypal_email and ('@' not in paypal_email or any(ch.isspace() for ch in paypal_email)):
            raise ExpenseError('INVALID_PAYPAL_EMAIL')
        with self.store.engine.begin() as connection:
            if group_id is not None:
                self._assert_group_member(connection, participant_id, group_id)
            friend_rows = {row['id']: row for row in connection.execute(select(expense_friends).where(
                expense_friends.c.owner_id == participant_id,
                expense_friends.c.id.in_([share['friend_id'] for share in clean_shares if share['friend_id']]))).mappings()}
            for share in clean_shares:
                if share['friend_id']:
                    friend = friend_rows.get(share['friend_id'])
                    if not friend or friend['name'] != share['name']:
                        raise ExpenseError('FRIEND_REFERENCE_MISMATCH', 400)
            split_id = identifier()
            connection.execute(insert(expense_splits).values(
                id=split_id, owner_id=participant_id, group_id=group_id, title=title, category=category,
                total_minor=total_minor, currency=currency, source=source,
                receipt_meta_json=_safe_json(receipt_meta), created_at=time.time()))
            if host_name or upi_id or paypal_email:
                connection.execute(insert(expense_split_payees).values(
                    split_id=split_id, host_name=host_name, upi_id=upi_id, paypal_email=paypal_email))
            for share in clean_shares:
                share_id = identifier()
                connection.execute(insert(expense_shares).values(
                    id=share_id, split_id=split_id, name=share['name'], amount_minor=share['amount_minor'],
                    is_payer=int(share['is_payer']), settled=int(share['is_payer']),
                    settled_at=time.time() if share['is_payer'] else None))
                if share['friend_id']:
                    friend = friend_rows[share['friend_id']]
                    connection.execute(insert(expense_share_contacts).values(
                        share_id=share_id, friend_id=friend['id'], whatsapp=friend['whatsapp'],
                        upi_id=friend['upi_id']))
        return self.get_split(participant_id, split_id)

    @staticmethod
    def equal_shares(names, payer_name, total_minor):
        """Convenience helper the route layer uses for the 'split equally' path."""
        if not isinstance(names, list) or not names:
            raise ExpenseError('INVALID_SHARES')
        amounts = split_equal_cents(total_minor, names)
        return [dict(name=n, amountMinor=amounts[n], isPayer=(n == payer_name)) for n in names]

    def get_split(self, participant_id, split_id):
        with self.store.engine.connect() as connection:
            split = connection.execute(select(expense_splits).where(
                expense_splits.c.id == split_id, expense_splits.c.owner_id == participant_id)).mappings().first()
            if not split:
                raise ExpenseError('SPLIT_NOT_FOUND', 404)
            shares = connection.execute(select(expense_shares).where(
                expense_shares.c.split_id == split_id).order_by(expense_shares.c.id)).mappings().all()
            contacts = _share_contacts(connection, shares)
            payee = connection.execute(select(expense_split_payees).where(
                expense_split_payees.c.split_id == split_id)).mappings().first()
        return _split_view(split, shares, contacts, payee)

    def list_splits(self, participant_id, *, group_id=ALL, limit=50):
        with self.store.engine.connect() as connection:
            query = select(expense_splits).where(expense_splits.c.owner_id == participant_id)
            if group_id is not ALL:
                query = query.where(expense_splits.c.group_id == group_id)
            splits = connection.execute(query.order_by(expense_splits.c.created_at.desc()).limit(limit)).mappings().all()
            result = []
            for split in splits:
                shares = connection.execute(select(expense_shares).where(
                    expense_shares.c.split_id == split['id']).order_by(expense_shares.c.id)).mappings().all()
                payee = connection.execute(select(expense_split_payees).where(
                    expense_split_payees.c.split_id == split['id'])).mappings().first()
                result.append(_split_view(split, shares, _share_contacts(connection, shares), payee))
        return result

    def groups_summary(self, participant_id):
        with self.store.engine.connect() as connection:
            memberships = connection.execute(select(workshop_groups.c.id, workshop_groups.c.name).join(
                group_memberships, group_memberships.c.group_id == workshop_groups.c.id).where(
                group_memberships.c.participant_id == participant_id)).all()
            counts = dict(connection.execute(select(expense_splits.c.group_id, func.count()).where(
                expense_splits.c.owner_id == participant_id).group_by(expense_splits.c.group_id)).all())
        groups = [dict(id=g.id, name=g.name, splitCount=counts.get(g.id, 0)) for g in memberships]
        groups.append(dict(id=None, name='Individual expenses', splitCount=counts.get(None, 0)))
        return groups

    def settle_share(self, participant_id, split_id, share_id, settled):
        with self.store.engine.begin() as connection:
            split = connection.execute(select(expense_splits.c.id).where(
                expense_splits.c.id == split_id, expense_splits.c.owner_id == participant_id)).first()
            if not split:
                raise ExpenseError('SPLIT_NOT_FOUND', 404)
            share = connection.execute(select(expense_shares.c.id, expense_shares.c.is_payer).where(
                expense_shares.c.id == share_id, expense_shares.c.split_id == split_id)).first()
            if not share:
                raise ExpenseError('SHARE_NOT_FOUND', 404)
            if share.is_payer:
                raise ExpenseError('PAYER_SHARE_ALWAYS_SETTLED', 409)
            connection.execute(update(expense_shares).where(expense_shares.c.id == share_id).values(
                settled=int(bool(settled)), settled_at=time.time() if settled else None))
        return self.get_split(participant_id, split_id)

    # ------------------------------------------------------------ subscriptions
    def list_subscriptions(self, participant_id):
        with self.store.engine.connect() as connection:
            subs = connection.execute(select(expense_subscriptions).where(
                expense_subscriptions.c.owner_id == participant_id).order_by(
                expense_subscriptions.c.billing_day)).mappings().all()
            result = []
            for sub in subs:
                participants = connection.execute(select(expense_subscription_participants).where(
                    expense_subscription_participants.c.subscription_id == sub['id'])).mappings().all()
                details = connection.execute(select(expense_subscription_details).where(
                    expense_subscription_details.c.subscription_id == sub['id'])).mappings().first()
                result.append(_subscription_view(sub, participants, details))
        return result

    def create_subscription(self, participant_id, name, monthly_amount_minor, billing_day, currency, participants,
                            *, host_name='', upi_id=''):
        name = _name(name, field='name', max_len=80)
        monthly_amount_minor = _amount_minor(monthly_amount_minor)
        if monthly_amount_minor == 0:
            raise ExpenseError('INVALID_AMOUNT_MINOR')
        if type(billing_day) is not int or not 1 <= billing_day <= 28:
            raise ExpenseError('INVALID_BILLING_DAY')
        if not isinstance(currency, str) or not currency.isalpha() or len(currency) != 3:
            raise ExpenseError('INVALID_CURRENCY')
        if not isinstance(participants, list) or len(participants) > 20:
            raise ExpenseError('INVALID_PARTICIPANTS')
        host_name = _name(host_name, field='host_name', required=False) if host_name else ''
        upi_id = _name(upi_id, field='upi_id', required=False) if upi_id else ''
        clean_participants = []
        for entry in participants:
            if not isinstance(entry, dict):
                raise ExpenseError('INVALID_PARTICIPANTS')
            clean_participants.append(dict(
                name=_name(entry.get('name'), field='participant_name'),
                whatsapp=_name(entry.get('whatsapp'), field='whatsapp', max_len=40, required=False) if entry.get('whatsapp') else ''))
        sub_id = identifier()
        with self.store.engine.begin() as connection:
            connection.execute(insert(expense_subscriptions).values(
                id=sub_id, owner_id=participant_id, name=name, monthly_amount_minor=monthly_amount_minor,
                currency=currency.upper(), billing_day=billing_day, created_at=time.time()))
            connection.execute(insert(expense_subscription_details).values(
                subscription_id=sub_id, host_name=host_name, upi_id=upi_id))
            for entry in clean_participants:
                connection.execute(insert(expense_subscription_participants).values(
                    id=identifier(), subscription_id=sub_id, name=entry['name'], whatsapp=entry['whatsapp']))
        return self.list_subscriptions(participant_id)

    def remove_subscription(self, participant_id, subscription_id):
        with self.store.engine.begin() as connection:
            owned = connection.execute(select(expense_subscriptions.c.id).where(
                expense_subscriptions.c.id == subscription_id,
                expense_subscriptions.c.owner_id == participant_id)).first()
            if not owned:
                raise ExpenseError('SUBSCRIPTION_NOT_FOUND', 404)
            connection.execute(delete(expense_subscription_participants).where(
                expense_subscription_participants.c.subscription_id == subscription_id))
            connection.execute(delete(expense_subscription_details).where(
                expense_subscription_details.c.subscription_id == subscription_id))
            connection.execute(delete(expense_subscriptions).where(expense_subscriptions.c.id == subscription_id))
        return self.list_subscriptions(participant_id)

    # -------------------------------------------------------------- analytics
    def analytics(self, participant_id):
        with self.store.engine.connect() as connection:
            rows = connection.execute(select(expense_splits.c.category, expense_splits.c.total_minor,
                expense_splits.c.created_at).where(expense_splits.c.owner_id == participant_id)).all()
        by_category, by_month, total_minor = {}, {}, 0
        for category, amount_minor, created_at in rows:
            by_category[category] = by_category.get(category, 0) + amount_minor
            month = time.strftime('%Y-%m', time.gmtime(created_at))
            by_month[month] = by_month.get(month, 0) + amount_minor
            total_minor += amount_minor
        return dict(totalMinor=total_minor, byCategory=by_category, byMonth=dict(sorted(by_month.items())),
                   splitCount=len(rows))


def _safe_json(value):
    import json
    try:
        encoded = json.dumps(value or {})
    except (TypeError, ValueError):
        return '{}'
    return encoded[:2000] if len(encoded) <= 2000 else '{}'


def _share_contacts(connection, shares):
    ids = [share['id'] for share in shares]
    if not ids:
        return {}
    return {row['share_id']: row for row in connection.execute(select(expense_share_contacts).where(
        expense_share_contacts.c.share_id.in_(ids))).mappings()}


def _split_view(split, shares, contacts=None, payee=None):
    contacts = contacts or {}
    share_views = [dict(id=s['id'], name=s['name'], amountMinor=s['amount_minor'],
                        isPayer=bool(s['is_payer']), settled=bool(s['settled']),
                        friendID=contacts[s['id']]['friend_id'] if s['id'] in contacts else None,
                        whatsapp=contacts[s['id']]['whatsapp'] if s['id'] in contacts else '',
                        upiID=contacts[s['id']]['upi_id'] if s['id'] in contacts else '') for s in shares]
    pending_minor = sum(s['amountMinor'] for s in share_views if not s['isPayer'] and not s['settled'])
    all_settled = all(s['settled'] for s in share_views)
    import json
    try:
        receipt_meta = json.loads(split['receipt_meta_json'])
    except (TypeError, ValueError):
        receipt_meta = {}
    return dict(id=split['id'], title=split['title'], category=split['category'], totalMinor=split['total_minor'],
               currency=split['currency'], source=split['source'], groupID=split['group_id'],
               createdAt=split['created_at'], shares=share_views, pendingMinor=pending_minor,
               allSettled=all_settled, receiptMeta=receipt_meta,
               payee=dict(hostName=payee['host_name'], upiID=payee['upi_id'], paypalEmail=payee['paypal_email'])
               if payee else dict(hostName='', upiID='', paypalEmail=''))


def _subscription_view(sub, participants, details=None):
    return dict(id=sub['id'], name=sub['name'], monthlyAmountMinor=sub['monthly_amount_minor'],
               currency=sub['currency'], billingDay=sub['billing_day'], createdAt=sub['created_at'],
               hostName=details['host_name'] if details else '', upiID=details['upi_id'] if details else '',
               participants=[dict(id=p['id'], name=p['name'], whatsapp=p['whatsapp']) for p in participants])
