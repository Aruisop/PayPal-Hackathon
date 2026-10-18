"""Embedding safety and math contracts; fake tensors are not model benchmarks."""

import hashlib
import io
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import model_assets
from semantic import LocalEncoder, SemanticUnavailable

try:
    import numpy as np
except ImportError:
    np = None


class AssetTests(unittest.TestCase):
    def test_invalid_profile_and_missing_local_assets(self):
        with self.assertRaises(ValueError):
            LocalEncoder('untrusted/model')
        with tempfile.TemporaryDirectory() as root:
            with patch('semantic.importlib.util.find_spec', return_value=object()), patch('urllib.request.urlopen', side_effect=AssertionError('network')):
                result = LocalEncoder(root=root).status()
        self.assertFalse(result['available'])
        self.assertFalse(result['loaded'])
        self.assertIn('assets are missing', result['reason'])

    def test_missing_dependencies_are_optional_and_no_runtime_load(self):
        with patch('semantic.importlib.util.find_spec', return_value=None), patch.object(LocalEncoder, '_load', side_effect=AssertionError('load')):
            self.assertIn('not installed', LocalEncoder().status()['reason'])

    def test_preparation_pins_and_verifies_before_publication(self):
        payloads = {'tokenizer.json': b'tokenizer fixture', 'onnx/model_quantized.onnx': b'public weights fixture'}
        profile = dict(model_assets.PROFILES['minilm'])
        profile['files'] = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
        requests = []

        def download(request, timeout):
            requests.append(request.full_url)
            self.assertIn('/resolve/' + profile['revision'] + '/', request.full_url)
            name = request.full_url.split(profile['revision'] + '/', 1)[1]
            return io.BytesIO(payloads[name])

        with tempfile.TemporaryDirectory() as root, patch.dict(model_assets.PROFILES, minilm=profile), patch('urllib.request.urlopen', side_effect=download):
            manifest = model_assets.prepare(root=root)
            self.assertEqual(2, len(requests))
            self.assertEqual('Apache-2.0', manifest['license'])
            model_assets.prepare(root=root)
            self.assertEqual(2, len(requests), 'Verified assets should not be downloaded again.')
            directory = model_assets.validate_assets(root=root, verify_hashes=True)
            # Same-length corruption evades the cheap status check but not runtime hashes.
            (directory / 'tokenizer.json').write_bytes(b'x' * len(payloads['tokenizer.json']))
            model_assets.validate_assets(root=root)
            with self.assertRaises(ValueError):
                model_assets.validate_assets(root=root, verify_hashes=True)

    def test_failed_integrity_never_publishes_manifest(self):
        profile = dict(model_assets.PROFILES['minilm'])
        profile['files'] = {'tokenizer.json': hashlib.sha256(b'expected').hexdigest()}
        with tempfile.TemporaryDirectory() as root, patch.dict(model_assets.PROFILES, minilm=profile), patch('urllib.request.urlopen', return_value=io.BytesIO(b'wrong')):
            with self.assertRaises(ValueError):
                model_assets.prepare(root=root)
            self.assertFalse((Path(root) / 'minilm' / 'manifest.json').exists())
            self.assertEqual([], list((Path(root) / 'minilm').glob('*.partial')))

    def test_description_uses_only_semantic_catalog_content(self):
        offer = {'id': 'private-reference', 'title': 'Night Orbit', 'description': 'A space adventure.',
                 'domain': 'movie', 'meta': '{"genre":"Sci-Fi","runtime_min":148}', 'price_minor': 999999}
        text = LocalEncoder.describe(offer)
        self.assertIn('Sci-Fi', text)
        self.assertNotIn('999999', text)
        self.assertNotIn('private-reference', text)
        self.assertNotIn('148', text)
        self.assertEqual('Quiet hike', LocalEncoder.describe({'title': 'Quiet hike', 'meta': 'invalid JSON'}))


class FakeTokenizer:
    def __init__(self):
        self.calls = 0
        self.truncation_disabled = False
        self.padding_disabled = False
        self.last_prefix = False

    def no_truncation(self):
        self.truncation_disabled = True

    def no_padding(self):
        self.padding_disabled = True

    def encode_batch(self, texts):
        self.calls += 1
        self.last_prefix = texts[0].startswith('Represent this sentence')
        result = []
        for text in texts:
            ids = [101] + [200] * len(text.split()) + [102]
            result.append(types.SimpleNamespace(ids=ids, attention_mask=[1] * len(ids), type_ids=[0] * len(ids)))
        return result


class FakeSession:
    def __init__(self):
        self.calls = 0
        self.inputs = None
        self.invalid = None

    def get_inputs(self):
        return [types.SimpleNamespace(name=name) for name in ('input_ids', 'attention_mask', 'token_type_ids')]

    def run(self, output_names, inputs):
        self.calls += 1
        self.inputs = inputs
        rows, tokens = inputs['input_ids'].shape
        output = np.zeros((rows, tokens, 384), dtype=np.float32)
        output[:, 0, 0] = 1
        output[:, 1:, 1] = 1
        # A large padded-token activation must never influence mean pooling.
        output[inputs['attention_mask'] == 0, :2] = 99
        if self.invalid == 'nan':
            output[0, 0, 0] = np.nan
        if self.invalid == 'zero':
            output.fill(0)
        if self.invalid == 'shape':
            output = output[:, :, :2]
        return [output]


@unittest.skipIf(np is None, 'Optional numpy dependency is absent; install requirements-ai.txt for tensor contracts.')
class EncoderTests(unittest.TestCase):
    def encoder(self, model='minilm', query_instruction=False):
        encoder = LocalEncoder(model=model, query_instruction=query_instruction)
        encoder._np = np
        encoder._tokenizer = FakeTokenizer()
        encoder._session = FakeSession()
        return encoder

    def test_masked_mean_pooling_excludes_padding_and_normalizes(self):
        encoder = self.encoder()
        vectors = encoder.encode(['a b', 'a'])
        self.assertTrue(np.allclose(vectors[0][:2], [1 / np.sqrt(10), 3 / np.sqrt(10)]))
        self.assertTrue(np.allclose(vectors[1][:2], [1 / np.sqrt(5), 2 / np.sqrt(5)]))
        self.assertTrue(np.allclose(np.linalg.norm(vectors, axis=1), 1))
        self.assertEqual(np.int64, encoder._session.inputs['input_ids'].dtype)

    def test_bge_cls_and_explicit_query_instruction_not_applied_to_catalog(self):
        encoder = self.encoder('bge', query_instruction=True)
        vector = encoder.encode(['quiet outdoor adventure'])[0]
        self.assertEqual([1, 0], vector[:2])
        self.assertTrue(encoder._tokenizer.last_prefix)
        encoder.catalog([{'title': 'Woodland walk', 'description': 'Quiet forest trails.'}])
        self.assertFalse(encoder._tokenizer.last_prefix)

    def test_private_queries_never_cached_catalog_reuse_and_content_invalidation(self):
        encoder = self.encoder()
        offer = {'id': 'one', 'title': 'Woodland walk', 'description': 'Quiet forest trails.'}
        first = encoder.catalog([offer, dict(offer)])
        self.assertEqual(1, encoder._session.calls)
        first[0][0] = 99
        self.assertNotEqual(99, encoder.catalog([offer])[0][0])
        for unused in range(3):
            encoder.encode(['private budget preference'])
        self.assertEqual(4, encoder._session.calls)
        self.assertEqual(1, len(encoder._catalog_cache))
        encoder.catalog([dict(offer, title='Changed title')])
        self.assertEqual(5, encoder._session.calls)
        self.assertEqual(2, len(encoder._catalog_cache))
        self.assertNotIn('private', repr(encoder._catalog_cache))

    def test_catalog_cache_is_bounded_separately_from_private_queries(self):
        encoder = self.encoder()
        for index in range(70):
            encoder.catalog([{'title': f'Public item {index}'}])
        self.assertEqual(64, len(encoder._catalog_cache))
        for unused in range(70):
            encoder.encode(['fresh private query'])
        self.assertEqual(64, len(encoder._catalog_cache))
        self.assertEqual({'encodeMs', 'textCount', 'catalogMisses'}, set(encoder.timings))

    def test_input_and_token_bounds_reject_without_silent_truncation(self):
        encoder = self.encoder()
        for texts in ([], [''], ['x' * 1001], ['x'] * 65, 'not a list'):
            with self.assertRaises(ValueError):
                encoder.encode(texts)
        encoder.encode(['x ' * 254])
        before = encoder._session.calls
        with self.assertRaisesRegex(ValueError, '256-token'):
            encoder.encode(['x ' * 255])
        self.assertEqual(before, encoder._session.calls)
        encoder.encode(['one'] * 64)
        with self.assertRaises(ValueError):
            encoder.catalog([{'title': 'one'}] * 21)

    def test_invalid_tensor_shapes_and_values_cannot_be_used_as_scores(self):
        for invalid in ('nan', 'zero', 'shape'):
            encoder = self.encoder()
            encoder._session.invalid = invalid
            with self.assertRaises(SemanticUnavailable):
                encoder.encode(['hello'])

    def test_loading_is_cpu_only_serial_and_disables_tokenizer_truncation(self):
        encoder = LocalEncoder()
        tokenizer = FakeTokenizer()
        options = types.SimpleNamespace()
        calls = []

        def session_factory(path, sess_options, providers):
            calls.append((path, sess_options, providers))
            return FakeSession()

        ort = types.SimpleNamespace(SessionOptions=lambda: options, InferenceSession=session_factory,
                                    ExecutionMode=types.SimpleNamespace(ORT_SEQUENTIAL='sequential'))
        tokens = types.SimpleNamespace(Tokenizer=types.SimpleNamespace(from_file=lambda path: tokenizer))
        with patch('semantic.validate_assets', return_value=Path('public-fixture')), patch.dict('sys.modules', onnxruntime=ort, tokenizers=tokens), patch('urllib.request.urlopen', side_effect=AssertionError('network')):
            encoder.encode(['hello'])
        self.assertEqual(['CPUExecutionProvider'], calls[0][2])
        self.assertEqual(1, options.intra_op_num_threads)
        self.assertEqual(1, options.inter_op_num_threads)
        self.assertEqual('sequential', options.execution_mode)
        self.assertTrue(tokenizer.truncation_disabled)
        self.assertTrue(tokenizer.padding_disabled)
        self.assertIn('loadMs', encoder.timings)

    def test_missing_assets_become_explicit_unavailable_without_network(self):
        with tempfile.TemporaryDirectory() as root, patch('urllib.request.urlopen', side_effect=AssertionError('network')):
            encoder = LocalEncoder(root=root)
            with self.assertRaises(SemanticUnavailable):
                encoder.encode(['hello'])
            self.assertFalse(encoder.status()['available'])
            self.assertIn('could not initialize', encoder.status()['reason'])


if __name__ == '__main__':
    unittest.main()
