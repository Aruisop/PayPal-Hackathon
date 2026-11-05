"""Small SQLAlchemy Core store shared by local SQLite and hosted PostgreSQL."""
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import (Column, Float, ForeignKey, Integer, MetaData, String, Table,
                        UniqueConstraint, create_engine, event, insert, select, update)

metadata = MetaData()
versions = Table('schema_versions', metadata, Column('id', Integer, primary_key=True),
                 Column('revision', Integer, nullable=False))
participants = Table('participants', metadata,
    Column('id', String(40), primary_key=True), Column('token_hash', String(64), unique=True, nullable=False),
    Column('csrf_token', String(64), nullable=False), Column('expires_at', Float, nullable=False))
workshops = Table('workshops', metadata,
    Column('id', String(40), primary_key=True), Column('title', String(160), nullable=False),
    Column('description', String(600), nullable=False), Column('starts_at', String(40), nullable=False),
    Column('ends_at', String(40), nullable=False), Column('price_minor', Integer, nullable=False),
    Column('currency', String(3), nullable=False), Column('lesson_key', String(40), nullable=False))
bookings = Table('bookings', metadata,
    Column('id', String(40), primary_key=True),
    Column('participant_id', ForeignKey('participants.id'), nullable=False),
    Column('workshop_id', ForeignKey('workshops.id'), nullable=False),
    Column('future_membership_id', String(40), nullable=True),
    Column('state', String(30), nullable=False), Column('active_attempt_id', String(40)),
    UniqueConstraint('participant_id', 'workshop_id', name='uq_participant_workshop'))
attempts = Table('payment_attempts', metadata,
    Column('id', String(40), primary_key=True), Column('booking_id', ForeignKey('bookings.id'), nullable=False),
    Column('state', String(30), nullable=False), Column('create_key', String(40), unique=True, nullable=False),
    Column('capture_key', String(40), unique=True, nullable=False),
    Column('order_id', String(40), unique=True), Column('capture_id', String(40), unique=True),
    Column('merchant_id', String(40), nullable=False), Column('price_minor', Integer, nullable=False),
    Column('currency', String(3), nullable=False), Column('created_at', Float, nullable=False),
    Column('capture_started_at', Float), Column('error', String(100)), Column('debug_id', String(100)),
    Column('lease_token', String(64)), Column('lease_until', Float, nullable=False, default=0))
entitlements = Table('entitlements', metadata,
    Column('booking_id', ForeignKey('bookings.id'), primary_key=True),
    Column('capture_id', String(40), unique=True, nullable=False), Column('granted_at', Float, nullable=False))
workshop_groups = Table('workshop_groups', metadata,
    Column('id', String(40), primary_key=True),
    Column('name', String(80), nullable=False),
    Column('organizer_id', ForeignKey('participants.id'), nullable=False),
    Column('invite_token', String(64), unique=True, nullable=False),
    Column('workshop_id', ForeignKey('workshops.id')),
    Column('created_at', Float, nullable=False))
group_memberships = Table('group_memberships', metadata,
    Column('id', String(40), primary_key=True),
    Column('group_id', ForeignKey('workshop_groups.id'), nullable=False),
    Column('participant_id', ForeignKey('participants.id'), nullable=False),
    Column('joined_at', Float, nullable=False),
    UniqueConstraint('group_id', 'participant_id', name='uq_group_participant'))

# Revision 3: Collaborative booking catalog, resources, shared purchases, and contributions
catalog_offers = Table('catalog_offers', metadata,
    Column('id', String(64), primary_key=True),
    Column('domain', String(30), nullable=False),  # 'movie' or 'excursion'
    Column('merchant_id', String(64), nullable=False),
    Column('title', String(160), nullable=False),
    Column('description', String(600), nullable=False),
    Column('schedule_time', String(40), nullable=False),  # ISO UTC
    Column('price_minor', Integer, nullable=False),  # per ticket/unit USD cents
    Column('currency', String(3), nullable=False, default='USD'),
    Column('meta_json', String(1000), nullable=False, default='{}'))

catalog_resources = Table('catalog_resources', metadata,
    Column('id', String(64), primary_key=True),
    Column('offer_id', ForeignKey('catalog_offers.id'), nullable=False),
    Column('resource_key', String(64), nullable=False),
    Column('label', String(40), nullable=False),
    Column('row_label', String(10), nullable=False),
    Column('col_number', Integer, nullable=False),
    Column('state', String(20), nullable=False, default='FREE'),  # FREE, HELD, ALLOCATED, ISSUED
    Column('held_by_purchase_id', String(40)),
    Column('held_until', Float),
    UniqueConstraint('offer_id', 'resource_key', name='uq_offer_resource'))

group_member_profiles = Table('group_member_profiles', metadata,
    Column('id', String(40), primary_key=True),
    Column('group_id', ForeignKey('workshop_groups.id'), nullable=False),
    Column('participant_id', ForeignKey('participants.id'), nullable=False),
    Column('alias', String(60), nullable=False),
    Column('consent_coarse_progress', Integer, nullable=False, default=1),
    Column('updated_at', Float, nullable=False),
    UniqueConstraint('group_id', 'participant_id', name='uq_group_profile_participant'))

group_member_preferences = Table('group_member_preferences', metadata,
    Column('id', String(40), primary_key=True),
    Column('group_id', ForeignKey('workshop_groups.id'), nullable=False),
    Column('participant_id', ForeignKey('participants.id'), nullable=False),
    Column('raw_text', String(1000), nullable=False),
    Column('interpreted_json', String(2000), nullable=False),
    Column('confirmed_constraints_json', String(2000)),
    Column('is_confirmed', Integer, nullable=False, default=0),
    Column('updated_at', Float, nullable=False),
    UniqueConstraint('group_id', 'participant_id', name='uq_group_pref_participant'))

shared_purchases = Table('shared_purchases', metadata,
    Column('id', String(40), primary_key=True),
    Column('group_id', ForeignKey('workshop_groups.id'), nullable=False),
    Column('offer_id', ForeignKey('catalog_offers.id'), nullable=False),
    Column('state', String(30), nullable=False, default='DRAFT'),
    Column('total_cents', Integer, nullable=False),
    Column('currency', String(3), nullable=False, default='USD'),
    Column('frozen_at', Float),
    Column('hold_deadline', Float),
    Column('policy', String(100), nullable=False, default='all_or_nothing_refund'),
    Column('fenced_claim_token', String(64)),
    Column('created_at', Float, nullable=False))

purchase_contributions = Table('purchase_contributions', metadata,
    Column('id', String(40), primary_key=True),
    Column('purchase_id', ForeignKey('shared_purchases.id'), nullable=False),
    Column('participant_id', ForeignKey('participants.id'), nullable=False),
    Column('alias', String(60), nullable=False),
    Column('share_cents', Integer, nullable=False),
    Column('assigned_resource_id', ForeignKey('catalog_resources.id')),
    Column('state', String(30), nullable=False, default='PENDING_CONSENT'),
    Column('consent_given_at', Float),
    Column('order_id', String(40)),
    Column('authorization_id', String(40)),
    Column('capture_id', String(40)),
    Column('create_request_id', String(64)),
    Column('authorize_request_id', String(64)),
    Column('void_request_id', String(64)),
    Column('capture_request_id', String(64)),
    Column('created_at', Float, nullable=False),
    UniqueConstraint('purchase_id', 'participant_id', name='uq_purchase_participant'))

group_tickets = Table('group_tickets', metadata,
    Column('id', String(40), primary_key=True),
    Column('purchase_id', ForeignKey('shared_purchases.id'), nullable=False),
    Column('contribution_id', ForeignKey('purchase_contributions.id'), nullable=False),
    Column('participant_id', ForeignKey('participants.id'), nullable=False),
    Column('resource_id', ForeignKey('catalog_resources.id'), nullable=False),
    Column('ticket_code', String(64), nullable=False, unique=True),
    Column('issued_at', Float, nullable=False),
    UniqueConstraint('purchase_id', 'participant_id', name='uq_ticket_purchase_participant'))

group_recovery_tasks = Table('group_recovery_tasks', metadata,
    Column('id', String(40), primary_key=True),
    Column('purchase_id', ForeignKey('shared_purchases.id'), nullable=False),
    Column('contribution_id', ForeignKey('purchase_contributions.id'), nullable=False),
    Column('action', String(20), nullable=False),
    Column('target_id', String(40), nullable=False),
    Column('state', String(20), nullable=False, default='PENDING'),
    Column('attempt_count', Integer, nullable=False, default=0),
    Column('last_error', String(200)),
    Column('updated_at', Float, nullable=False))

# Revision 4 is additive. Historical Slice 3 records are retained for review;
# they cannot establish payment evidence for the corrected coordinator.
group_workflows = Table('group_workflows', metadata,
    Column('purchase_id', ForeignKey('shared_purchases.id'), primary_key=True),
    Column('lease_token', String(64)),
    Column('lease_until', Float, nullable=False, default=0),
    Column('merchant_id', String(64), nullable=False, default=''),
    Column('cancel_requested', Integer, nullable=False, default=0),
    Column('finalization_requested', Integer, nullable=False, default=0),
    Column('review_required', Integer, nullable=False, default=0),
    Column('error', String(100)),
    Column('updated_at', Float, nullable=False))

group_operations = Table('group_operations', metadata,
    Column('id', String(40), primary_key=True),
    Column('purchase_id', ForeignKey('shared_purchases.id'), nullable=False),
    Column('contribution_id', ForeignKey('purchase_contributions.id'), nullable=False),
    Column('kind', String(20), nullable=False),
    Column('request_id', String(40), unique=True, nullable=False),
    Column('target_id', String(64)),
    Column('provider_id', String(64)),
    Column('state', String(20), nullable=False),
    Column('error', String(100)),
    Column('started_at', Float, nullable=False),
    Column('updated_at', Float, nullable=False),
    UniqueConstraint('contribution_id', 'kind', name='uq_contribution_operation'))

# Revision 5: shared discussion is independent of private preferences/payments.
room_messages = Table('room_messages', metadata,
    Column('id', String(40), primary_key=True),
    Column('group_id', ForeignKey('workshop_groups.id'), nullable=False, index=True),
    Column('participant_id', ForeignKey('participants.id'), nullable=False),
    Column('text', String(1000), nullable=False),
    Column('created_at', Float, nullable=False))

# Revision 6: informal expense splitting. These are IOU-style personal ledgers,
# never PayPal-authoritative money. No table here can grant inventory, tickets
# or payment state; settlement is a manual, participant-confirmed note only.
expense_profiles = Table('expense_profiles', metadata,
    Column('participant_id', ForeignKey('participants.id'), primary_key=True),
    Column('display_name', String(80), nullable=False, default=''),
    Column('upi_id', String(80), nullable=False, default=''),
    Column('updated_at', Float, nullable=False))

expense_friends = Table('expense_friends', metadata,
    Column('id', String(40), primary_key=True),
    Column('owner_id', ForeignKey('participants.id'), nullable=False, index=True),
    Column('name', String(80), nullable=False),
    Column('upi_id', String(80), nullable=False, default=''),
    Column('whatsapp', String(40), nullable=False, default=''),
    Column('created_at', Float, nullable=False),
    UniqueConstraint('owner_id', 'name', name='uq_expense_friend_owner_name'))

expense_splits = Table('expense_splits', metadata,
    Column('id', String(40), primary_key=True),
    Column('owner_id', ForeignKey('participants.id'), nullable=False, index=True),
    Column('group_id', ForeignKey('workshop_groups.id'), nullable=True),
    Column('title', String(160), nullable=False),
    Column('category', String(20), nullable=False, default='other'),
    Column('total_minor', Integer, nullable=False),
    Column('currency', String(3), nullable=False, default='USD'),
    Column('source', String(10), nullable=False, default='manual'),
    Column('receipt_meta_json', String(2000), nullable=False, default='{}'),
    Column('created_at', Float, nullable=False))

expense_shares = Table('expense_shares', metadata,
    Column('id', String(40), primary_key=True),
    Column('split_id', ForeignKey('expense_splits.id'), nullable=False, index=True),
    Column('name', String(80), nullable=False),
    Column('amount_minor', Integer, nullable=False),
    Column('is_payer', Integer, nullable=False, default=0),
    Column('settled', Integer, nullable=False, default=0),
    Column('settled_at', Float, nullable=True))

expense_subscriptions = Table('expense_subscriptions', metadata,
    Column('id', String(40), primary_key=True),
    Column('owner_id', ForeignKey('participants.id'), nullable=False, index=True),
    Column('name', String(80), nullable=False),
    Column('monthly_amount_minor', Integer, nullable=False),
    Column('currency', String(3), nullable=False, default='USD'),
    Column('billing_day', Integer, nullable=False),
    Column('created_at', Float, nullable=False))

expense_subscription_participants = Table('expense_subscription_participants', metadata,
    Column('id', String(40), primary_key=True),
    Column('subscription_id', ForeignKey('expense_subscriptions.id'), nullable=False, index=True),
    Column('name', String(80), nullable=False),
    Column('whatsapp', String(40), nullable=False, default=''))

# Revision 7: contact snapshots for new ledger shares. Historical name-only
# shares stay untouched; a deleted contact cannot silently redirect a reminder.
expense_share_contacts = Table('expense_share_contacts', metadata,
    Column('share_id', ForeignKey('expense_shares.id'), primary_key=True),
    Column('friend_id', String(40), nullable=False),
    Column('whatsapp', String(40), nullable=False, default=''),
    Column('upi_id', String(80), nullable=False, default=''))

expense_split_payees = Table('expense_split_payees', metadata,
    Column('split_id', ForeignKey('expense_splits.id'), primary_key=True),
    Column('host_name', String(80), nullable=False, default=''),
    Column('upi_id', String(80), nullable=False, default=''),
    Column('paypal_email', String(160), nullable=False, default=''))

expense_subscription_details = Table('expense_subscription_details', metadata,
    Column('subscription_id', ForeignKey('expense_subscriptions.id'), primary_key=True),
    Column('host_name', String(80), nullable=False, default=''),
    Column('upi_id', String(80), nullable=False, default=''))


def identifier():
    return secrets.token_hex(16)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def money(minor):
    return f'{minor // 100}.{minor % 100:02d}'


def split_equal_cents(total_cents, participant_ids):
    """Computes exact integer USD cent shares for participants in stable order.

    Guarantees: sum(shares.values()) == total_cents strictly.
    Example: 10000 cents ($100.00) among 3 -> [3334, 3333, 3333]
    """
    n = len(participant_ids)
    if n <= 0:
        raise ValueError('Cannot split among zero participants')
    base = total_cents // n
    remainder = total_cents % n
    result = {}
    for i, pid in enumerate(participant_ids):
        result[pid] = base + (1 if i < remainder else 0)
    return result


class Store:
    def __init__(self, url):
        if url.startswith('postgres://'):
            url = 'postgresql+psycopg://' + url[len('postgres://'):]
        elif url.startswith('postgresql://'):
            url = 'postgresql+psycopg://' + url[len('postgresql://'):]
        if url.startswith('sqlite:///'):
            path = url[len('sqlite:///'):]
            if path != ':memory:':
                Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, pool_pre_ping=True,
            connect_args={'check_same_thread': False, 'timeout': 10} if url.startswith('sqlite:') else {})
        if self.engine.dialect.name == 'sqlite':
            @event.listens_for(self.engine, 'connect')
            def sqlite_settings(connection, _):
                connection.execute('PRAGMA foreign_keys=ON')
                connection.execute('PRAGMA busy_timeout=10000')

    def migrate(self, target=2):
        # Target defaults to 2 to preserve Slice 2 backward compatibility contract.
        from sqlalchemy import inspect
        if target not in (2, 3, 4, 5, 6, 7):
            raise ValueError('Supported migration targets are 2 through 7')
        if 'schema_versions' in inspect(self.engine).get_table_names():
            with self.engine.begin() as connection:
                revision = connection.execute(select(versions.c.revision).where(versions.c.id == 1)).scalar()
                if revision == 1:
                    workshop_groups.create(connection, checkfirst=True)
                    group_memberships.create(connection, checkfirst=True)
                    revision = 2
                    connection.execute(versions.update().where(versions.c.id == 1).values(revision=2))
                if revision == 2 and target >= 3:
                    catalog_offers.create(connection, checkfirst=True)
                    catalog_resources.create(connection, checkfirst=True)
                    group_member_profiles.create(connection, checkfirst=True)
                    group_member_preferences.create(connection, checkfirst=True)
                    shared_purchases.create(connection, checkfirst=True)
                    purchase_contributions.create(connection, checkfirst=True)
                    group_tickets.create(connection, checkfirst=True)
                    group_recovery_tasks.create(connection, checkfirst=True)
                    revision = 3
                    connection.execute(versions.update().where(versions.c.id == 1).values(revision=3))
                if revision == 3 and target >= 4:
                    group_workflows.create(connection, checkfirst=True)
                    group_operations.create(connection, checkfirst=True)
                    for purchase in connection.execute(select(shared_purchases)).mappings():
                        connection.execute(insert(group_workflows).values(
                            purchase_id=purchase['id'], lease_until=0, merchant_id='',
                            cancel_requested=0, review_required=1,
                            error='LEGACY_PURCHASE_REQUIRES_REVIEW', updated_at=time.time()))
                    revision = 4
                    connection.execute(versions.update().where(versions.c.id == 1).values(revision=4))
                if revision == 4 and target >= 5:
                    room_messages.create(connection, checkfirst=True)
                    revision = 5
                    connection.execute(versions.update().where(versions.c.id == 1).values(revision=5))
                if revision == 5 and target >= 6:
                    expense_profiles.create(connection, checkfirst=True)
                    expense_friends.create(connection, checkfirst=True)
                    expense_splits.create(connection, checkfirst=True)
                    expense_shares.create(connection, checkfirst=True)
                    expense_subscriptions.create(connection, checkfirst=True)
                    expense_subscription_participants.create(connection, checkfirst=True)
                    revision = 6
                    connection.execute(versions.update().where(versions.c.id == 1).values(revision=6))
                if revision == 6 and target >= 7:
                    expense_share_contacts.create(connection, checkfirst=True)
                    expense_split_payees.create(connection, checkfirst=True)
                    expense_subscription_details.create(connection, checkfirst=True)
                    revision = 7
                    connection.execute(versions.update().where(versions.c.id == 1).values(revision=7))
                if revision not in (2, 3, 4, 5, 6, 7):
                    raise RuntimeError('Unsupported database revision; run the documented migration')
            return
        tables = [versions, participants, workshops, bookings, attempts, entitlements,
                  workshop_groups, group_memberships]
        if target >= 3:
            tables += [catalog_offers, catalog_resources, group_member_profiles, group_member_preferences,
                       shared_purchases, purchase_contributions, group_tickets, group_recovery_tasks]
        if target >= 4:
            tables += [group_workflows, group_operations]
        if target >= 5:
            tables += [room_messages]
        if target >= 6:
            tables += [expense_profiles, expense_friends, expense_splits, expense_shares,
                       expense_subscriptions, expense_subscription_participants]
        if target >= 7:
            tables += [expense_share_contacts, expense_split_payees, expense_subscription_details]
        metadata.create_all(self.engine, tables=tables)
        with self.engine.begin() as connection:
            connection.execute(insert(versions).values(id=1, revision=target))

    def seed(self):
        from sqlalchemy import inspect
        with self.engine.begin() as connection:
            # Seed workshops if empty
            if not connection.execute(select(workshops.c.id).limit(1)).first():
                today = datetime.now(timezone.utc).date()
                first = datetime.combine(today + timedelta(days=7 + (6 - today.weekday()) % 7),
                                         datetime.min.time(), timezone.utc).replace(hour=13)
                records = [
                    ('interview-basics', 'Coding interviews: the first steps',
                     'A beginner-friendly online workshop on problem solving and explaining your approach.',
                     first, 2500, 'interview'),
                    ('web-basics', 'Build your first web page',
                     'Learn HTML and CSS through a small guided project, with no prior experience required.',
                     first + timedelta(days=7), 1800, 'web'),
                ]
                for key, title, description, start, price, lesson in records:
                    connection.execute(insert(workshops).values(id=key, title=title, description=description,
                        starts_at=start.isoformat(), ends_at=(start + timedelta(hours=1)).isoformat(),
                        price_minor=price, currency='USD', lesson_key=lesson))

            # Seed collaborative booking catalog if table exists and is empty
            # Check before selecting: catching a missing-table error leaves a
            # PostgreSQL transaction aborted, even when Python catches it.
            if inspect(connection).has_table('catalog_offers'):
                # Development convenience (seed() never runs in production): a database older than its
                # sample sessions would show an empty catalog, so roll fully elapsed sessions forward by whole
                # weeks. Weekday and time are preserved; resources, prices and merchants are untouched.
                now = datetime.now(timezone.utc)
                stored = connection.execute(select(catalog_offers.c.id, catalog_offers.c.schedule_time)).all()
                parsed = [(oid, datetime.fromisoformat(stamp.replace('Z', '+00:00'))) for oid, stamp in stored]
                if parsed and all(moment <= now for _, moment in parsed):
                    for oid, moment in parsed:
                        weeks = (now - moment).days // 7 + 1
                        connection.execute(update(catalog_offers).where(catalog_offers.c.id == oid).values(
                            schedule_time=(moment + timedelta(weeks=weeks)).isoformat()))
            has_offers = (not inspect(connection).has_table('catalog_offers') or
                          bool(connection.execute(select(catalog_offers.c.id).limit(1)).first()))
            if not has_offers:
                today = datetime.now(timezone.utc).date()
                friday = datetime.combine(today + timedelta(days=(4 - today.weekday()) % 7 or 7),
                                          datetime.min.time(), timezone.utc).replace(hour=19, minute=30)
                saturday = datetime.combine(today + timedelta(days=(5 - today.weekday()) % 7 or 7),
                                            datetime.min.time(), timezone.utc).replace(hour=21, minute=0)
                sunday = datetime.combine(today + timedelta(days=(6 - today.weekday()) % 7 or 7),
                                          datetime.min.time(), timezone.utc).replace(hour=14, minute=0)

                offers_data = [
                    ('movie-cosmic-odyssey-fri', 'movie', 'fictional-cinema-operator',
                     'Cosmic Odyssey: Remastered',
                     'Sci-fi epic restored in 4K. Starlight Cinema Screen 1.',
                     friday.isoformat(), 1600, 'USD',
                     '{"auditorium": "Screen 1", "runtime_min": 148, "genre": "Sci-Fi"}'),
                    ('movie-neon-shadows-sat', 'movie', 'fictional-cinema-operator',
                     'Neon Shadows: Director Cut',
                     'Cyberpunk mystery thriller. Starlight Cinema Screen 2.',
                     saturday.isoformat(), 2000, 'USD',
                     '{"auditorium": "Screen 2", "runtime_min": 125, "genre": "Thriller"}'),
                    ('movie-silent-echoes-sun', 'movie', 'fictional-cinema-operator',
                     'Silent Echoes (Matinee)',
                     'Award-winning acoustic drama. Starlight Cinema Screen 1.',
                     sunday.isoformat(), 1200, 'USD',
                     '{"auditorium": "Screen 1", "runtime_min": 105, "genre": "Drama"}'),
                    ('excursion-kayak-canyon-sat', 'excursion', 'cascade-trail-operator',
                     'Emerald River Kayak Expedition',
                     'Guided 3-hour river paddle through scenic canyon gorges.',
                     saturday.replace(hour=9, minute=0).isoformat(), 10000, 'USD',
                     '{"operator": "Cascade Adventures", "capacity": 4, "type": "fixed_group"}'),
                    ('excursion-mountain-trek-sun', 'excursion', 'cascade-trail-operator',
                     'Alpine Ridge Sunset Trek',
                     'Guided alpine trail with panoramic summit views.',
                     sunday.replace(hour=15, minute=0).isoformat(), 12000, 'USD',
                     '{"operator": "Cascade Adventures", "capacity": 4, "type": "fixed_group"}'),
                ]
                for oid, dom, mid, title, desc, stime, pminor, curr, meta in offers_data:
                    connection.execute(insert(catalog_offers).values(
                        id=oid, domain=dom, merchant_id=mid, title=title, description=desc,
                        schedule_time=stime, price_minor=pminor, currency=curr, meta_json=meta))

                    if dom == 'movie':
                        row = 'A' if 'fri' in oid else ('B' if 'sat' in oid else 'C')
                        for col in range(1, 9):
                            connection.execute(insert(catalog_resources).values(
                                id=f'res-{oid}-{row}{col}', offer_id=oid,
                                resource_key=f'{oid}:{row}{col}', label=f'Seat {row}{col}',
                                row_label=row, col_number=col, state='FREE'))
                    else:
                        for place_idx in range(1, 5):
                            connection.execute(insert(catalog_resources).values(
                                id=f'res-{oid}-P{place_idx}', offer_id=oid,
                                resource_key=f'{oid}:place-{place_idx}', label=f'Place #{place_idx}',
                                row_label='G', col_number=place_idx, state='FREE'))

    def participant(self, token):
        if not token or len(token) != 64:
            return None
        with self.engine.connect() as connection:
            row = connection.execute(select(participants).where(
                participants.c.token_hash == token_hash(token), participants.c.expires_at > time.time())).mappings().first()
            return dict(row) if row else None

    def new_participant(self):
        token = secrets.token_hex(32)
        record = dict(id=identifier(), token_hash=token_hash(token), csrf_token=secrets.token_hex(32),
                      expires_at=time.time() + 30 * 86400)
        with self.engine.begin() as connection:
            connection.execute(insert(participants).values(**record))
        return record, token

    def catalog(self):
        with self.engine.connect() as connection:
            rows = connection.execute(select(workshops).order_by(workshops.c.starts_at)).mappings().all()
            return [dict(id=r['id'], title=r['title'], description=r['description'],
                         startsAt=r['starts_at'], endsAt=r['ends_at'], value=money(r['price_minor']),
                         currency=r['currency']) for r in rows]

    def offers(self, domain=None):
        with self.engine.connect() as connection:
            query = select(catalog_offers)
            if domain:
                query = query.where(catalog_offers.c.domain == domain)
            rows = connection.execute(query.order_by(catalog_offers.c.schedule_time)).mappings().all()
            results = []
            for r in rows:
                resources = connection.execute(select(catalog_resources).where(
                    catalog_resources.c.offer_id == r['id']).order_by(
                    catalog_resources.c.col_number)).mappings().all()
                results.append(dict(
                    id=r['id'], domain=r['domain'], merchantID=r['merchant_id'],
                    title=r['title'], description=r['description'],
                    scheduleTime=r['schedule_time'], priceMinor=r['price_minor'],
                    value=money(r['price_minor']), currency=r['currency'],
                    meta=r['meta_json'],
                    resources=[dict(id=res['id'], key=res['resource_key'],
                                    label=res['label'], row=res['row_label'],
                                    col=res['col_number'], state=res['state']) for res in resources]))
            return results

