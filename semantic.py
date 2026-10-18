"""Optional local CPU embeddings; hard booking decisions belong to Planning.

No network I/O occurs here. Install requirements-ai.txt and explicitly prepare
assets with model_assets.py. Only trusted catalog descriptions are cached;
participant text and vectors are never retained by this module.
"""

from collections import OrderedDict
import hashlib
import importlib.util
import json
import math
import threading
import time

from model_assets import PROFILES, validate_assets


class SemanticUnavailable(RuntimeError):
    """Local inference cannot run; callers must label any alternative honestly."""


class LocalEncoder:
    def __init__(self, model='minilm', root=None, query_instruction=False):
        if model not in PROFILES:
            raise ValueError('Choose the minilm or bge model profile.')
        self.model = model
        self.root = root
        self.profile = PROFILES[model]
        self.query_instruction = bool(query_instruction)
        self._lock = threading.RLock()
        self._session = None
        self._tokenizer = None
        self._np = None
        self._load_error = None
        self._catalog_cache = OrderedDict()
        self.timings = {}

    def status(self):
        """Cheap readiness inspection, without importing/loading model runtimes."""
        result = {
            'available': False, 'model': self.profile['repository'],
            'profile': self.model, 'revision': self.profile['revision'],
            'engine': 'local_onnx_q8', 'loaded': self._session is not None,
            'queryInstruction': self.query_instruction,
        }
        if self._load_error:
            result['reason'] = self._load_error
            return result
        if any(importlib.util.find_spec(name) is None for name in ('numpy', 'onnxruntime', 'tokenizers')):
            result['reason'] = 'Optional local AI dependencies are not installed.'
            return result
        try:
            validate_assets(self.model, self.root)
        except ValueError as error:
            result['reason'] = str(error)
            return result
        result.update(available=True, reason='Local assets prepared; inference loads on first use.')
        return result

    def _load(self):
        if self._session is not None:
            return
        if self._load_error:
            raise SemanticUnavailable(self._load_error)
        started = time.perf_counter()
        try:
            directory = validate_assets(self.model, self.root, verify_hashes=True)
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
            options = ort.SessionOptions()
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            session = ort.InferenceSession(str(directory / 'onnx' / 'model_quantized.onnx'),
                                           sess_options=options, providers=['CPUExecutionProvider'])
            tokenizer = Tokenizer.from_file(str(directory / 'tokenizer.json'))
            tokenizer.no_truncation()
            tokenizer.no_padding()
            self._np, self._tokenizer, self._session = np, tokenizer, session
            self.timings['loadMs'] = round((time.perf_counter() - started) * 1000, 3)
        except Exception as error:
            self._load_error = 'Local AI could not initialize; check prepared assets and optional CPU dependencies.'
            raise SemanticUnavailable(self._load_error) from error

    @staticmethod
    def _validate_texts(texts, maximum=64):
        if not isinstance(texts, (list, tuple)) or not 1 <= len(texts) <= maximum:
            raise ValueError(f'Provide between 1 and {maximum} text items.')
        if any(not isinstance(text, str) or not text.strip() or len(text) > 1000 for text in texts):
            raise ValueError('Each text must contain 1 to 1000 characters.')

    def encode(self, texts):
        """Embed up to 64 private text items without caching or logging them.

        No text is silently truncated. A token overflow requires clarification.
        Optional BGE query instruction is applied here, never to catalog items.
        """
        self._validate_texts(texts)
        with self._lock:
            self._load()
            prefix = self.profile['query_prefix'] if self.query_instruction else ''
            return self._encode([prefix + text for text in texts])

    def _encode(self, texts):
        started = time.perf_counter()
        try:
            encoded = self._tokenizer.encode_batch(texts)
            limit = self.profile['max_tokens']
            if any(len(item.ids) > limit for item in encoded):
                raise ValueError(f'An item exceeds the {limit}-token model limit; shorten or split the preference.')
            length = max(len(item.ids) for item in encoded)
            arrays = {
                'input_ids': [item.ids + [0] * (length - len(item.ids)) for item in encoded],
                'attention_mask': [item.attention_mask + [0] * (length - len(item.ids)) for item in encoded],
                'token_type_ids': [item.type_ids + [0] * (length - len(item.ids)) for item in encoded],
            }
            np = self._np
            names = {item.name for item in self._session.get_inputs()}
            if not names or not names.issubset(arrays):
                raise SemanticUnavailable('The prepared model has unsupported inputs.')
            inputs = {name: np.asarray(arrays[name], dtype=np.int64) for name in names}
            output = self._session.run(None, inputs)[0]
            if output.shape != (len(texts), length, self.profile['dimension']) or not np.isfinite(output).all():
                raise SemanticUnavailable('The local model returned invalid embeddings.')
            if self.profile['pooling'] == 'cls':
                pooled = output[:, 0, :]
            else:
                mask = np.asarray(arrays['attention_mask'], dtype=np.float32)[..., None]
                pooled = (output * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1)
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            if not np.isfinite(norms).all() or (norms <= 1e-12).any():
                raise SemanticUnavailable('The local model returned an empty embedding.')
            result = (pooled / norms).tolist()
            if any(not all(math.isfinite(value) for value in vector) for vector in result):
                raise SemanticUnavailable('The local model returned invalid embeddings.')
            self.timings.update(encodeMs=round((time.perf_counter() - started) * 1000, 3), textCount=len(texts))
            return result
        except ValueError:
            raise
        except SemanticUnavailable:
            raise
        except Exception as error:
            raise SemanticUnavailable('Local inference failed; no recommendation confidence is available.') from error

    @staticmethod
    def describe(offer):
        """Semantic text from trusted catalog fields, excluding prices and IDs."""
        if not isinstance(offer, dict):
            raise ValueError('A trusted catalog offer is required.')
        meta = offer.get('meta', {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except ValueError:
                meta = {}
        genre = meta.get('genre', '') if isinstance(meta, dict) else ''
        parts = [offer.get('title', ''), offer.get('description', ''), offer.get('domain', ''), genre]
        text = '. '.join(value.strip() for value in parts if isinstance(value, str) and value.strip())
        LocalEncoder._validate_texts([text])
        return text

    def catalog(self, offers):
        """Cache only trusted catalog content; return vectors in input order.

        The 64-entry content cache is independent from all participant inference.
        Returned copies prevent callers changing a cached vector accidentally.
        """
        if not isinstance(offers, (list, tuple)) or not 1 <= len(offers) <= 20:
            raise ValueError('Provide between 1 and 20 trusted catalog offers.')
        texts = [self.describe(offer) for offer in offers]
        keys = [hashlib.sha256(text.encode('utf-8')).hexdigest() for text in texts]
        with self._lock:
            self._load()
            missing = OrderedDict((key, text) for key, text in zip(keys, texts) if key not in self._catalog_cache)
            if missing:
                vectors = self._encode(list(missing.values()))
                for key, vector in zip(missing, vectors):
                    self._catalog_cache[key] = tuple(vector)
            for key in keys:
                self._catalog_cache.move_to_end(key)
            while len(self._catalog_cache) > 64:
                self._catalog_cache.popitem(last=False)
            self.timings['catalogMisses'] = len(missing)
            return [list(self._catalog_cache[key]) for key in keys]
