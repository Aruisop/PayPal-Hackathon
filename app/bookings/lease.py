"""Database-backed exclusive leases with fenced writes, without network I/O."""
import time
from contextlib import contextmanager

from sqlalchemy import select, update

from app.shared.errors import BookingError
from storage import group_workflows, identifier

LEASE_SECONDS = 120


class BookingLease:
    def __init__(self, store, purchase_id, token):
        self.store, self.purchase_id, self.token = store, purchase_id, token

    def check(self, connection):
        # Updating first serializes the check with claims by other workers.
        claimed = connection.execute(update(group_workflows).where(
            group_workflows.c.purchase_id == self.purchase_id,
            group_workflows.c.lease_token == self.token,
            group_workflows.c.lease_until > time.time()).values(updated_at=time.time()))
        if claimed.rowcount != 1:
            raise BookingError('STALE_OPERATION', 409)

    @contextmanager
    def write(self):
        with self.store.engine.begin() as connection:
            self.check(connection)
            yield connection

    def renew(self):
        with self.write() as connection:
            connection.execute(update(group_workflows).where(
                group_workflows.c.purchase_id == self.purchase_id).values(
                lease_until=time.time() + LEASE_SECONDS))


@contextmanager
def claim_booking(store, purchase_id):
    token = identifier()
    with store.engine.begin() as connection:
        result = connection.execute(update(group_workflows).where(
            group_workflows.c.purchase_id == purchase_id,
            group_workflows.c.lease_until <= time.time()).values(
            lease_token=token, lease_until=time.time() + LEASE_SECONDS, updated_at=time.time()))
        if result.rowcount != 1:
            raise BookingError('BOOKING_OPERATION_IN_PROGRESS', 409)
        workflow = connection.execute(select(group_workflows).where(
            group_workflows.c.purchase_id == purchase_id)).mappings().one()
        if workflow['review_required']:
            # Roll back the claim as well. No legacy financial fact is discarded.
            raise BookingError('LEGACY_PURCHASE_REQUIRES_REVIEW', 409)
    try:
        yield BookingLease(store, purchase_id, token)
    finally:
        with store.engine.begin() as connection:
            connection.execute(update(group_workflows).where(
                group_workflows.c.purchase_id == purchase_id,
                group_workflows.c.lease_token == token).values(lease_token=None, lease_until=0))

