"""Small SQLAlchemy Core store shared by local SQLite and hosted PostgreSQL."""
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import (Column, Float, ForeignKey, Integer, MetaData, String, Table,
                        UniqueConstraint, create_engine, event, insert, select)

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


def identifier():
    return secrets.token_hex(16)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def money(minor):
    return f'{minor // 100}.{minor % 100:02d}'


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

    def migrate(self):
        # Revision 1 is immutable. Future changes must add a migration here.
        from sqlalchemy import inspect
        if 'schema_versions' in inspect(self.engine).get_table_names():
            with self.engine.connect() as connection:
                revision = connection.execute(select(versions.c.revision).where(versions.c.id == 1)).scalar()
            if revision != 1:
                raise RuntimeError('Unsupported database revision; run the documented migration')
            return
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(insert(versions).values(id=1, revision=1))

    def seed(self):
        with self.engine.begin() as connection:
            if connection.execute(select(workshops.c.id).limit(1)).first():
                return
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
