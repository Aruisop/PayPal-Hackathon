"""Development seed data must never leave the demo catalog empty."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, update

from app.shared.storage import Store, catalog_offers


class CatalogRefreshTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store('sqlite:///' + (Path(self.directory.name) / 'seed.db').as_posix())
        self.store.migrate(target=6)
        self.store.seed()

    def tearDown(self):
        self.store.engine.dispose()
        self.directory.cleanup()

    def stamps(self):
        with self.store.engine.connect() as connection:
            return {row.id: datetime.fromisoformat(row.schedule_time) for row in
                    connection.execute(select(catalog_offers.c.id, catalog_offers.c.schedule_time))}

    def test_elapsed_sessions_roll_forward_keeping_weekday_and_time(self):
        past = {oid: moment - timedelta(weeks=9) for oid, moment in self.stamps().items()}
        with self.store.engine.begin() as connection:
            for oid, moment in past.items():
                connection.execute(update(catalog_offers).where(catalog_offers.c.id == oid).values(
                    schedule_time=moment.isoformat()))
        self.store.seed()
        now = datetime.now(timezone.utc)
        for oid, moment in self.stamps().items():
            self.assertGreater(moment, now)
            self.assertEqual((moment.weekday(), moment.hour, moment.minute),
                             (past[oid].weekday(), past[oid].hour, past[oid].minute))
            self.assertLessEqual(moment - now, timedelta(weeks=1))

    def test_upcoming_catalog_is_left_untouched(self):
        before = self.stamps()
        self.store.seed()
        self.assertEqual(before, self.stamps())


if __name__ == '__main__':
    unittest.main()
