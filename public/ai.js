'use strict';
(function (root) {
  function describe(offer) {
    return [offer.title, offer.description, offer.domain === 'movie' ? 'cinema movie screening' : 'outdoor adventure excursion',
      typeof offer.meta === 'object' ? JSON.stringify(offer.meta) : offer.meta].filter(Boolean).join('. ').slice(0, 1000);
  }
  function keywordRank(query, offers) {
    const stopWords = new Set(['a', 'an', 'the', 'i', 'we', 'our', 'my', 'would', 'like', 'want', 'something', 'for', 'with', 'and', 'or', 'to', 'of', 'in', 'at', 'is', 'it']);
    const words = [...new Set(String(query).toLowerCase().match(/[a-z0-9]+/g) || [])].filter((word) => !stopWords.has(word));
    return offers.map((offer) => ({id: offer.id, score: words.reduce((sum, word) => sum + Number(describe(offer).toLowerCase().includes(word)), 0)}))
      .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
  }
  function create({makeWorker = () => new Worker('/ai-worker.mjs', {type: 'module'}), onStatus = () => {}, timeout = 120000} = {}) {
    let worker = null, ready = false, nextID = 0, enabling = null;
    const pending = new Map();
    function reset(message) {
      if (worker) worker.terminate();
      worker = null; ready = false; enabling = null;
      for (const value of pending.values()) { clearTimeout(value.timer); value.reject(new Error(message)); }
      pending.clear(); onStatus(message, 'unavailable');
    }
    function request(type, data = {}) {
      return new Promise((resolve, reject) => {
        const id = ++nextID;
        const timer = setTimeout(() => reset('AI loading timed out. Basic search remains available; enable AI to retry.'), timeout);
        pending.set(id, {resolve, reject, timer});
        worker.postMessage({id, type, ...data});
      });
    }
    async function enable() {
      if (ready) return;
      if (enabling) return enabling;
      onStatus('Loading on-device AI. First use downloads the model and runtime.', 'loading');
      try {
        if (!worker) {
          worker = makeWorker();
          worker.onmessage = ({data}) => {
            if (data.type === 'progress') { onStatus(data.message, 'loading'); return; }
            const value = pending.get(data.id);
            if (!value) return;
            clearTimeout(value.timer); pending.delete(data.id);
            if (data.type === 'error') value.reject(new Error(data.message)); else value.resolve(data);
          };
          worker.onerror = () => reset('AI assets could not load. Basic search works; check your connection and enable AI to retry.');
        }
        enabling = request('load').then((result) => {
          if (result.type !== 'ready') throw new Error('AI did not finish initializing. Enable AI to retry.');
          ready = true; onStatus('On-device AI ready · your search text stays on this device', 'ready');
        })
          .catch((error) => { reset(error.message); throw error; });
        await enabling;
      } catch (error) { if (worker) reset(error.message); throw error; }
    }
    async function rank(query, offers) {
      if (!ready) throw new Error('Enable on-device AI first.');
      if (typeof query !== 'string' || !query.trim() || query.length > 1000 || !Array.isArray(offers) || offers.length > 20) throw new Error('Use a description of 1–1000 characters.');
      const result = await request('rank', {query: query.trim(), offers: offers.map((offer) => ({id: offer.id, text: describe(offer)}))});
      const ids = new Set(offers.map((offer) => offer.id));
      if (result.type !== 'ranked' || !Array.isArray(result.ranked) || result.ranked.length !== ids.size ||
        new Set(result.ranked.map((item) => item.id)).size !== ids.size ||
        result.ranked.some((item) => !ids.has(item.id) || !Number.isFinite(item.score) || item.score < -1 || item.score > 1)) {
        throw new Error('AI returned an invalid ranking. Use basic search or retry.');
      }
      return result.ranked;
    }
    return {enable, rank, isReady: () => ready, disable: () => reset('On-device AI is off. Basic search is available.')};
  }
  const api = {create, describe, keywordRank};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.GroupPayAI = api;
})(typeof window === 'undefined' ? globalThis : window);
