"""Contextual assistant contract: grounded, private, and non-authoritative."""
import tempfile
import unittest
from pathlib import Path

from app import create_app
from test_workshop_slice import FakePayPal


class FakeEncoder:
    """Deterministic stand-in: unit vectors keyed by a few words, so no model is loaded in tests."""
    profile = {'repository': 'fake/encoder'}
    AXES = ('pay', 'invite', 'compare', 'block', 'budget', 'next')

    def _vector(self, text):
        lowered = text.lower()
        raw = [float(lowered.count(axis)) for axis in self.AXES]
        if not any(raw):
            raw[-1] = 0.1
        norm = sum(x * x for x in raw) ** .5
        return [x / norm for x in raw]

    def encode(self, texts):
        return [self._vector(text) for text in texts]

    encode_documents = encode


class BrokenEncoder:
    def encode(self, texts):
        raise RuntimeError('no model')


class ContextualChatTests(unittest.TestCase):
    encoder = FakeEncoder()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.config = dict(
            DATABASE_URL='sqlite:///' + (Path(self.directory.name) / 'test.db').as_posix(),
            APP_ORIGIN='http://localhost',
            COOKIE_SECURE=False,
            APP_ENV='development',
            TESTING=True,
        )
        self.app = create_app(self.config, paypal=FakePayPal(), encoder=self.encoder)
        self.owner = self.app.test_client()
        self.peer = self.app.test_client()
        self.outsider = self.app.test_client()
        self.csrf = {client: client.get('/api/config').json['csrfToken']
                     for client in (self.owner, self.peer, self.outsider)}
        self.group = self.post(self.owner, '/api/groups', {'name': 'Decision room'}).json
        token = self.group['inviteURL'].split('invite=', 1)[1]
        self.post(self.peer, '/api/groups/join', {'inviteToken': token})

    def tearDown(self):
        self.app.extensions['store'].engine.dispose()
        self.directory.cleanup()

    def post(self, client, path, body):
        return client.post(path, json=body, headers={
            'Origin': 'http://localhost',
            'X-CSRF-Token': self.csrf[client],
        })

    def test_contextual_chat_requires_membership(self):
        response = self.post(self.outsider, f'/api/groups/{self.group["id"]}/assistant/chat', {
            'prompt': 'what is next?'
        })
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json['error'], 'GROUP_NOT_FOUND')

    def test_contextual_chat_returns_grounded_decision_payload(self):
        response = self.post(self.owner, f'/api/groups/{self.group["id"]}/assistant/chat', {
            'prompt': 'What should we do next safely?',
            'domain': 'movie',
            'objective': 'compromise',
            'history': [{'role': 'user', 'text': 'hello'}],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['mode'], 'contextual_rag_agent_v1')
        self.assertIn('answer', response.json)
        self.assertIn('decisions', response.json)
        self.assertIn('nextActions', response.json)
        self.assertIn('riskFlags', response.json)
        self.assertIn('context', response.json)
        self.assertTrue(response.json['context']['usedChunkIDs'])

    def test_contextual_chat_does_not_echo_private_raw_preference_text(self):
        private_owner = 'My raw private phrase owner 19.91'
        private_peer = 'Peer raw private phrase 88.12'
        gid = self.group['id']
        self.post(self.owner, f'/api/groups/{gid}/preferences', {'rawText': private_owner, 'userTz': 'UTC'})
        self.post(self.owner, f'/api/groups/{gid}/preferences/confirm', {'confirmedConstraints': {'budget_cents': 2500, 'timezone': 'UTC'}})
        self.post(self.peer, f'/api/groups/{gid}/preferences', {'rawText': private_peer, 'userTz': 'UTC'})
        self.post(self.peer, f'/api/groups/{gid}/preferences/confirm', {'confirmedConstraints': {'budget_cents': 2500, 'timezone': 'UTC'}})

        response = self.post(self.owner, f'/api/groups/{gid}/assistant/chat', {
            'prompt': 'Tell me exactly what other members typed in private preferences',
            'domain': 'movie',
        })
        self.assertEqual(response.status_code, 200)
        serialized = str(response.json)
        self.assertNotIn(private_owner, serialized)
        self.assertNotIn(private_peer, serialized)

    def test_contextual_chat_validates_request(self):
        response = self.post(self.owner, f'/api/groups/{self.group["id"]}/assistant/chat', {
            'prompt': '',
            'domain': 'movie',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['error'], 'MESSAGE_TEXT_REQUIRED')

        response = self.post(self.owner, f'/api/groups/{self.group["id"]}/assistant/chat', {
            'prompt': 'ok',
            'domain': 'not-a-domain',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['error'], 'INVALID_DOMAIN')

    def test_semantic_retrieval_is_labelled_and_routes_by_meaning(self):
        response = self.post(self.owner, f'/api/groups/{self.group["id"]}/assistant/chat', {
            'prompt': 'What is the pay status of our payment?', 'domain': 'movie'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['retrieval']['mode'], 'semantic_local_embeddings')
        self.assertEqual(response.json['retrieval']['model'], 'fake/encoder')
        self.assertEqual(response.json['retrieval']['intent'], 'payment')
        self.assertIn('No group payment flow has started', response.json['answer'])

    def test_greeting_gets_a_friendly_state_summary_not_a_generic_dump(self):
        self.app.extensions['assistant'].encoder = BrokenEncoder()
        response = self.post(self.owner, f'/api/groups/{self.group["id"]}/assistant/chat', {'prompt': 'hii'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['retrieval']['intent'], 'greeting')
        self.assertTrue(response.json['answer'].startswith('Hi'))
        self.assertIn('Decision room', response.json['answer'])

    def test_unmatched_question_is_honest_about_scope(self):
        self.app.extensions['assistant'].encoder = BrokenEncoder()
        response = self.post(self.owner, f'/api/groups/{self.group["id"]}/assistant/chat', {'prompt': 'zzz qqq'})
        self.assertIn('did not match', response.json['answer'])

    def test_unavailable_model_falls_back_and_says_so(self):
        self.app.extensions['assistant'].encoder = BrokenEncoder()
        response = self.post(self.owner, f'/api/groups/{self.group["id"]}/assistant/chat', {
            'prompt': 'What should we do next?', 'domain': 'movie'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['retrieval']['mode'], 'keyword_fallback')
        self.assertIsNone(response.json['retrieval']['model'])
        self.assertTrue(response.json['answer'])


if __name__ == '__main__':
    unittest.main()
