'use strict';
// Test client/worker boundaries with controlled model output, not real inference.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const AI = require('../public/ai.js');
const offers = [{id: 'river', domain: 'excursion', title: 'River trail'}, {id: 'space', domain: 'movie', title: 'Cosmic Odyssey'}];
const workers = [], states = [];
class Worker {
  constructor() { this.messages = []; workers.push(this); }
  postMessage(value) { this.messages.push(value); }
  reply(value) { this.onmessage({data: value}); }
  terminate() { this.terminated = true; }
  last() { return this.messages.at(-1); }
}
const client = AI.create({makeWorker: () => new Worker(), onStatus: (...args) => states.push(args)});

(async () => {
  assert.equal(workers.length, 0, 'No model or runtime download before explicit enabling');
  await assert.rejects(client.rank('stars', offers), /Enable/);
  const enabling = client.enable(), worker = workers[0];
  assert.equal(client.isReady(), false);
  assert.equal(worker.last().type, 'load');
  worker.reply({id: worker.last().id, type: 'ready'}); await enabling;
  assert.equal(client.isReady(), true);
  await client.enable(); assert.equal(workers.length, 1, 'Repeated enabling reuses the loaded worker');

  let ranking = client.rank('quiet night under the stars', offers), message = worker.last();
  assert.equal(message.query, 'quiet night under the stars');
  assert.deepEqual(Object.keys(message.offers[0]).sort(), ['id', 'text'], 'Worker receives no budgets, participant IDs or financial data');
  worker.reply({id: message.id, type: 'ranked', ranked: [{id: 'space', score: .9}, {id: 'river', score: .2}]});
  assert.equal((await ranking)[0].id, 'space');
  for (const bad of [
    [{id: 'invented', score: .9}, {id: 'river', score: .2}],
    [{id: 'space', score: .9}, {id: 'space', score: .2}],
    [{id: 'space', score: Infinity}, {id: 'river', score: .2}],
    [{id: 'space', score: 2}, {id: 'river', score: .2}],
    [{id: 'space', score: .9}],
    {length: 2},
  ]) {
    ranking = client.rank('stars', offers); message = worker.last();
    worker.reply({id: message.id, type: 'ranked', ranked: bad});
    await assert.rejects(ranking, /invalid ranking/);
  }
  await assert.rejects(client.rank('x'.repeat(1001), offers));
  assert.equal(AI.keywordRank('I would like a river adventure', offers)[0].id, 'river');
  assert.ok(AI.keywordRank('zzzzzzz', offers).every((item) => item.score === 0));

  ranking = client.rank('river', offers); worker.onerror();
  await assert.rejects(ranking, /assets could not load/);
  assert.equal(client.isReady(), false); assert.equal(worker.terminated, true);
  const retry = client.enable(), retryWorker = workers[1];
  retryWorker.reply({id: retryWorker.last().id, type: 'ready'}); await retry;
  assert.equal(client.isReady(), true, 'Asset failure can be retried');
  client.disable(); assert.equal(client.isReady(), false);

  // Run the actual worker handler with deterministic embeddings. No model or HTTP.
  const replies = [], embedded = [], modelOptions = [];
  const workerSource = fs.readFileSync(path.join(__dirname, '../public/ai-worker.mjs'), 'utf8').replace(/^import .*;$/m, '');
  const self = {postMessage: (value) => replies.push(value)};
  const sandbox = vm.createContext({self, env: {backends: {onnx: {wasm: {}}}}, pipeline: async (task, model, options) => {
    modelOptions.push({task, model, options});
    return async (text) => { embedded.push(text); return {tolist: () => [text === 'space' ? [0, 1] : [1, 0]]}; };
  }});
  new vm.Script(workerSource).runInContext(sandbox);
  const dispatch = async (data) => { self.onmessage({data}); await new vm.Script('queue').runInContext(sandbox); return replies.at(-1); };
  assert.equal((await dispatch({id: 1, type: 'rank', query: 'river', offers: []})).type, 'error');
  assert.equal((await dispatch({id: 2, type: 'load'})).type, 'ready');
  assert.equal(modelOptions[0].options.dtype, 'q8');
  const result = await dispatch({id: 3, type: 'rank', query: 'river', offers: [{id: 'a', text: 'space'}, {id: 'b', text: 'river'}]});
  assert.equal(result.ranked[0].id, 'b'); assert.equal(result.ranked[0].score, 1);
  await dispatch({id: 4, type: 'rank', query: 'river', offers: [{id: 'b', text: 'river'}]});
  assert.equal(embedded.filter((item) => item === 'river').length, 1, 'Embeddings are reused only inside worker memory');
  assert.equal((await dispatch({id: 5, type: 'rank', query: 'x'.repeat(1001), offers: []})).type, 'error');
  console.log('AI loading, retry, disable, bounded catalog-only rankings and actual worker handler contracts passed. Embeddings mocked; no real model inference claimed.');
})().catch((error) => { client.disable(); console.error(error); process.exitCode = 1; });
