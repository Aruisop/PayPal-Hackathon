"""Removed evaluator mutations cannot alter catalog or issue payment evidence."""
import unittest

import test_phase4_fulfillment as fulfillment
from sqlalchemy import select
from app.shared.storage import catalog_resources, group_tickets


class RemovedSimulationTests(unittest.TestCase):
    setUp = fulfillment.Phase4FulfillmentTests.setUp
    tearDown = fulfillment.Phase4FulfillmentTests.tearDown
    post = fulfillment.Phase4FulfillmentTests.post
    create_authorized_group = fulfillment.Phase4FulfillmentTests.create_authorized_group

    def test_demo_cannot_reclaim_paid_seats_or_issue_synthetic_tickets(self):
        group_id = self.create_authorized_group()
        self.assertEqual(self.post(self.organizer, f'/api/groups/{group_id}/finalize', {}).json['state'], 'CONFIRMED')
        for scenario in ('happy_path', 'chaos_failure'):
            response = self.post(self.outsider, '/api/demo/run', dict(scenario=scenario, domain='movie'))
            self.assertEqual(response.status_code, 404)
        with self.app.extensions['store'].engine.connect() as connection:
            self.assertEqual(len(connection.execute(select(group_tickets)).all()), 2)
            self.assertEqual(connection.execute(select(catalog_resources.c.state).where(
                catalog_resources.c.id == 'res-movie-cosmic-odyssey-fri-A1')).scalar_one(), 'BOOKED')
        self.assertEqual(self.organizer.get(f'/api/groups/{group_id}/ticket').status_code, 200)
