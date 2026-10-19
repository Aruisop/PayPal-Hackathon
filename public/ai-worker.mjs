// Model assets download only after the user enables AI. Preference text is
// embedded here, on the device; it is never sent to an inference endpoint.
import {pipeline, env} from 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1/dist/transformers.min.js';

env.allowLocalModels = false;
env.backends.onnx.wasm.numThreads = 1;
const MODEL = 'Xenova/all-MiniLM-L6-v2';
const REVISION = 'da5f6eac91a9596269707e15ec694e50e25a0d14';
let extractor = null;
let loading = null;
let queue = Promise.resolve();
const vectors = new Map();

async function load() {
  if (extractor) return;
  if (!loading) loading = pipeline('feature-extraction', MODEL, {
    device: 'wasm', dtype: 'q8', revision: REVISION,
    progress_callback(event) {
      if (event.status === 'progress') self.postMessage({type: 'progress', message: `Loading AI assets${Number.isFinite(event.progress) ? ` · ${Math.floor(event.progress)}% of current file` : ''}`});
    },
  }).then((value) => { extractor = value; }).catch((error) => { loading = null; throw error; });
  await loading;
}
async function embed(text) {
  if (!vectors.has(text)) {
    const output = await extractor(text, {pooling: 'mean', normalize: true});
    vectors.set(text, output.tolist()[0]);
    if (vectors.size > 64) vectors.delete(vectors.keys().next().value);
  }
  return vectors.get(text);
}
function validText(value) { return typeof value === 'string' && value.length > 0 && value.length <= 1000; }
async function handle({id, type, query, offers}) {
  if (!Number.isSafeInteger(id)) return;
  try {
    if (type === 'load') {
      await load(); self.postMessage({id, type: 'ready', model: MODEL}); return;
    }
    if (type !== 'rank' || !extractor || !validText(query) || !Array.isArray(offers) || offers.length > 20 ||
      offers.some((offer) => !validText(offer.id) || !validText(offer.text))) throw new Error('Invalid AI request.');
    const queryVector = await embed(query);
    const ranked = [];
    for (const offer of offers) {
      const vector = await embed(offer.text);
      const score = vector.reduce((sum, value, index) => sum + value * queryVector[index], 0);
      if (!Number.isFinite(score)) throw new Error('Invalid model output.');
      ranked.push({id: offer.id, score: Math.max(-1, Math.min(1, score))});
    }
    ranked.sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
    self.postMessage({id, type: 'ranked', ranked, model: MODEL});
  } catch {
    self.postMessage({id, type: 'error', message: 'On-device AI could not run. Basic search and verified planning still work. Check your connection and try enabling AI again.'});
  }
}
self.onmessage = (event) => { queue = queue.then(() => handle(event.data)).catch(() => {}); };
