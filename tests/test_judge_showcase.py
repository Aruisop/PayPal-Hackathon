"""Test suite for Hackathon Judge Showcase Simulation & Chaos Recovery."""
import tempfile
import unittest
from pathlib import Path

from server import create_app
from storage import catalog_resources, group_recovery_tasks, group_tickets, shared_purchases
from test_workshop_slice import FakePayPal


class JudgeShowcaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.fake = FakePayPal()
        self.config = dict(
            DATABASE_URL='sqlite:///' + (Path(self.directory.name) / 'showcase.db').as_posix(),
            APP_ORIGIN='http://localhost',
            COOKIE_SECURE=False,
            APP_ENV='development',
            TESTING=True
        )
        self.app = create_app(self.config, paypal=self.fake)
        self.client = self.app.test_client()
        self.csrf = self.client.get('/api/config').json['csrfToken']

    def tearDown(self):
        self.app.extensions['store'].engine.dispose()
        self.directory.cleanup()

    def post(self, path, body):
        return self.client.post(path, json=body, headers={
            'Origin': 'http://localhost',
            'X-CSRF-Token': self.csrf
        })

    def test_happy_path_simulation_issues_three_private_tickets(self):
        resp = self.post('/api/demo/run', {'scenario': 'happy_path', 'domain': 'movie'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json
        self.assertTrue(data['success'])
        self.assertEqual(data['scenario'], 'happy_path')
        self.assertEqual(len(data['tickets']), 3)
        self.assertEqual(len(data['telemetry']), 6)

        # Check tickets exist in database
        store = self.app.extensions['store']
        with store.engine.connect() as conn:
            from sqlalchemy import select
            tickets = conn.execute(select(group_tickets)).mappings().all()
            self.assertEqual(len(tickets), 3)

            # Check purchase state is CONFIRMED
            purchase = conn.execute(select(shared_purchases).where(
                shared_purchases.c.id == tickets[0]['purchase_id'])).mappings().first()
            self.assertEqual(purchase['state'], 'CONFIRMED')

            # Check seats are BOOKED
            seats = conn.execute(select(catalog_resources.c.state).where(
                catalog_resources.c.id.in_([t['resource_id'] for t in tickets]))).scalars().all()
            self.assertTrue(all(s == 'BOOKED' for s in seats))

    def test_chaos_failure_simulation_triggers_compensatory_rollback(self):
        resp = self.post('/api/demo/run', {'scenario': 'chaos_failure', 'domain': 'movie'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json
        self.assertTrue(data['success'])
        self.assertEqual(data['scenario'], 'chaos_failure')
        self.assertIn('Auto-Refunded', data['recovery']['alice'])
        self.assertIn('Auto-Refunded', data['recovery']['bob'])
        self.assertIn('Voided', data['recovery']['charlie'])

        # Check recovery tasks exist in database
        store = self.app.extensions['store']
        with store.engine.connect() as conn:
            from sqlalchemy import select
            tasks = conn.execute(select(group_recovery_tasks)).mappings().all()
            self.assertEqual(len(tasks), 3)

            # Zero tickets issued
            tickets = conn.execute(select(group_tickets)).mappings().all()
            self.assertEqual(len(tickets), 0)

            # Purchase state is CANCELLED
            purchase = conn.execute(select(shared_purchases).where(
                shared_purchases.c.group_id == data['groupID'])).mappings().first()
            self.assertEqual(purchase['state'], 'CANCELLED')

            # Seats released back to FREE
            seats = conn.execute(select(catalog_resources.c.state).where(
                catalog_resources.c.id.in_(['res-movie-cosmic-odyssey-fri-A1', 'res-movie-cosmic-odyssey-fri-A2', 'res-movie-cosmic-odyssey-fri-A3']))).scalars().all()
            self.assertTrue(all(s == 'FREE' for s in seats))


if __name__ == '__main__':
    unittest.main()
