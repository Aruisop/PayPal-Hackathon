"""Group access and independent booking tests; PayPal is a stateful fake."""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import insert, inspect, select

from server import create_app
from storage import (Store, attempts, bookings, entitlements, group_memberships,
                     participants, versions, workshops)
from test_workshop_slice import FakePayPal


class GroupSliceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.fake = FakePayPal()
        self.config = dict(DATABASE_URL='sqlite:///' + (Path(self.directory.name) / 'test.db').as_posix(),
                           APP_ORIGIN='http://localhost', COOKIE_SECURE=False, APP_ENV='development', TESTING=True)
        self.app = create_app(self.config, paypal=self.fake)
        self.organizer = self.app.test_client()
        self.member = self.app.test_client()
        self.outsider = self.app.test_client()
        self.csrf = {client: client.get('/api/config').json['csrfToken']
                     for client in (self.organizer, self.member, self.outsider)}

    def tearDown(self):
        self.app.extensions['store'].engine.dispose()
        self.directory.cleanup()

    def post(self, client, path, body):
        return client.post(path, json=body, headers={'Origin': 'http://localhost',
            'X-CSRF-Token': self.csrf[client]})

    def group(self):
        created = self.post(self.organizer, '/api/groups', {'name': 'Friday friends'})
        self.assertEqual(created.status_code, 200)
        return created.json

    def join(self, group):
        token = group['inviteURL'].split('invite=', 1)[1]
        return self.post(self.member, '/api/groups/join', {'inviteToken': token})

    def test_invite_is_membership_only_and_repeat_join_is_safe(self):
        group = self.group()
        self.assertEqual(self.outsider.get(f'/api/groups/{group["id"]}').status_code, 404)
        self.assertEqual(self.post(self.outsider, f'/api/groups/{group["id"]}/selection',
                                   {'workshopID': 'web-basics'}).status_code, 404)
        first = self.join(group)
        second = self.join(group)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json['id'], second.json['id'])
        self.assertEqual(second.json['memberCount'], 2)
        self.assertNotIn('inviteURL', second.json)
        self.assertEqual(self.outsider.get('/api/groups').json['groups'], [])
        self.assertEqual(self.post(self.outsider, '/api/groups/join', {'inviteToken': 'bad'}).status_code, 404)
        with self.app.extensions['store'].engine.connect() as connection:
            self.assertEqual(len(connection.execute(select(group_memberships).where(
                group_memberships.c.group_id == group['id'])).all()), 2)

    def test_only_organizer_selects_once_from_trusted_catalog(self):
        group = self.group()
        self.join(group)
        path = f'/api/groups/{group["id"]}/selection'
        self.assertEqual(self.post(self.member, path, {'workshopID': 'web-basics'}).status_code, 403)
        self.assertEqual(self.post(self.organizer, path, {'workshopID': 'made-up'}).status_code, 404)
        chosen = self.post(self.organizer, path, {'workshopID': 'web-basics', 'amount': '0.01'})
        self.assertEqual(chosen.status_code, 200)
        self.assertEqual(chosen.json['workshopID'], 'web-basics')
        self.assertEqual(self.post(self.organizer, path, {'workshopID': 'web-basics'}).status_code, 200)
        self.assertEqual(self.post(self.organizer, path, {'workshopID': 'interview-basics'}).status_code, 409)
        self.assertEqual(self.member.get(f'/api/groups/{group["id"]}').json['workshopID'], 'web-basics')

    def test_two_profiles_pay_independently_and_see_only_own_status(self):
        group = self.group()
        self.join(group)
        self.post(self.organizer, f'/api/groups/{group["id"]}/selection', {'workshopID': 'interview-basics'})
        a = self.post(self.organizer, '/api/orders', {'workshopID': 'interview-basics', 'amount': '0.01'}).json
        b = self.post(self.member, '/api/orders', {'workshopID': 'interview-basics'}).json
        self.assertNotEqual(a['id'], b['id'])
        self.assertNotEqual(a['orderID'], b['orderID'])
        self.assertEqual(self.fake.create_calls, 2)
        self.assertEqual(self.fake.orders[a['orderID']]['purchase_units'][0]['amount']['value'], '25.00')
        self.fake.approve(a['orderID'])
        paid = self.post(self.organizer, f'/api/orders/{a["orderID"]}/capture', {}).json
        self.assertEqual(paid['attemptState'], 'COMPLETED')
        self.fake.approve(b['orderID'])
        self.fake.capture_status = 'PENDING'
        pending = self.post(self.member, f'/api/orders/{b["orderID"]}/capture', {}).json
        self.assertEqual(pending['attemptState'], 'PENDING')
        own_a = self.organizer.get(f'/api/groups/{group["id"]}').json['myBooking']
        own_b = self.member.get(f'/api/groups/{group["id"]}').json['myBooking']
        self.assertEqual(own_a['id'], a['id'])
        self.assertEqual(own_a['attemptState'], 'COMPLETED')
        self.assertEqual(own_b['id'], b['id'])
        self.assertEqual(own_b['attemptState'], 'PENDING')
        self.assertIsNone(own_b['lessonURL'])
        self.assertEqual(self.member.get(f'/api/bookings/{a["id"]}').status_code, 404)
        self.assertEqual(self.member.get(f'/lessons/{a["id"]}').status_code, 404)
        self.assertEqual(self.member.get(f'/lessons/{b["id"]}').status_code, 403)
        self.assertEqual(self.organizer.get(f'/lessons/{a["id"]}').status_code, 200)
        self.assertEqual(self.post(self.member, f'/api/orders/{a["orderID"]}/capture', {}).status_code, 404)

    def test_concurrent_repeat_join_has_one_membership(self):
        group = self.group()
        token = group['inviteURL'].split('invite=', 1)[1]
        participant = self.app.extensions['store'].participant(
            self.member.get_cookie('workshop_session').value)['id']
        groups = self.app.extensions['groups']
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: groups.join(participant, token), range(2)))
        self.assertEqual([result['id'] for result in results], [group['id'], group['id']])
        self.assertEqual(results[-1]['memberCount'], 2)

    def test_group_survives_restart_with_same_participant_session(self):
        group = self.group()
        self.join(group)
        self.post(self.organizer, f'/api/groups/{group["id"]}/selection', {'workshopID': 'web-basics'})
        restarted = create_app(self.config, paypal=self.fake)
        visitor = restarted.test_client()
        visitor.set_cookie('workshop_session', self.member.get_cookie('workshop_session').value)
        saved = visitor.get(f'/api/groups/{group["id"]}')
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json['workshopID'], 'web-basics')
        self.assertEqual(saved.json['memberCount'], 2)
        restarted.extensions['store'].engine.dispose()

    def test_revision_one_migrates_without_changing_prior_tables(self):
        path = Path(self.directory.name) / 'old.db'
        store = Store('sqlite:///' + path.as_posix())
        for table in (versions, participants, workshops, bookings, attempts, entitlements):
            table.create(store.engine)
        with store.engine.begin() as connection:
            connection.execute(insert(versions).values(id=1, revision=1))
            connection.execute(insert(participants).values(id='prior', token_hash='hash',
                csrf_token='csrf', expires_at=9999999999))
        store.migrate()
        store.migrate()
        with store.engine.connect() as connection:
            self.assertEqual(connection.execute(select(versions.c.revision)).scalar_one(), 2)
            self.assertEqual(connection.execute(select(participants.c.id)).scalar_one(), 'prior')
        self.assertIn('group_memberships', inspect(store.engine).get_table_names())
        store.engine.dispose()


if __name__ == '__main__':
    unittest.main()
