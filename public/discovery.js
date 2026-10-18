'use strict';
(function (root) {
  const $ = (id) => document.getElementById(id);
  const node = (tag, text, cls) => {
    const value = document.createElement(tag);
    if (text !== undefined) value.textContent = text;
    if (cls) value.className = cls;
    return value;
  };
  const price = (cents) => new Intl.NumberFormat(undefined, {style: 'currency', currency: 'USD'}).format(cents / 100);
  let offers = [], filter = 'all', query = '', scores = null, rankingMode = 'basic', sequence = 0, onPlan;
  let scout = null, loading = false;
  function art(domain, index) {
    const palettes = [['#24325d', '#7883ba', '#d2c0ab'], ['#845c79', '#bf879b', '#f3d3a6'], ['#367270', '#94b49f', '#e8d9ad']];
    const [bg, hill, sun] = palettes[index % palettes.length];
    const shape = domain === 'movie'
      ? `<circle cx="190" cy="77" r="40" fill="${sun}"/><ellipse cx="190" cy="77" rx="85" ry="19" fill="none" stroke="${hill}" stroke-width="8" transform="rotate(-22 190 77)"/><circle cx="80" cy="45" r="2" fill="#fff9"/><circle cx="280" cy="40" r="2" fill="#fff9"/><circle cx="320" cy="110" r="3" fill="#fff9"/><path d="M0 175L100 124L170 154L270 105L360 172V200H0Z" fill="${hill}" opacity=".55"/>`
      : `<circle cx="265" cy="62" r="36" fill="${sun}"/><path d="M0 145L100 40L178 130L255 75L360 163V200H0Z" fill="${hill}"/><path d="M0 190L100 109L180 169L280 120L360 176V200H0Z" fill="#1d4f5066"/><path d="M190 150Q140 173 220 200H310Q200 165 225 150Z" fill="#d7e4e8"/><path d="M57 151V80M35 120L57 83L80 120M29 139L57 102L84 139" stroke="#234e4b" fill="#234e4b" stroke-width="3"/>`;
    return `<svg viewBox="0 0 360 200" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><rect width="360" height="200" fill="${bg}"/>${shape}</svg>`;
  }
  function candidates() {
    const people = Number($('scout-people').value || 3), raw = $('scout-budget').value;
    if (![2, 3, 4].includes(people)) throw new Error('Choose 2–4 people.');
    if (raw !== '' && !/^\d+(\.\d{1,2})?$/.test(raw)) throw new Error('Use a nonnegative budget with at most two decimal places.');
    const ceiling = raw === '' ? null : Math.round(Number(raw) * 100);
    if (ceiling !== null && !Number.isSafeInteger(ceiling)) throw new Error('Budget is too large.');
    return offers.filter((offer) => Date.parse(offer.scheduleTime) > Date.now() &&
      (filter === 'all' || offer.domain === filter) &&
      (ceiling === null || (offer.domain === 'movie' ? offer.priceMinor : Math.ceil(offer.priceMinor / people)) <= ceiling));
  }
  function render(newFilter, newOffers) {
    if (newFilter) filter = newFilter;
    if (newOffers) offers = newOffers;
    const container = $('catalog-offers-grid'); container.replaceChildren();
    let visible;
    try { visible = candidates(); } catch (error) { $('catalog-result-note').textContent = error.message; return; }
    let mode = 'basic';
    if (query && scores) {
      const positions = new Map(scores.map((item, index) => [item.id, index]));
      visible.sort((a, b) => (positions.get(a.id) ?? 999) - (positions.get(b.id) ?? 999));
      if (rankingMode === 'basic') visible = visible.filter((offer) => scores.find((item) => item.id === offer.id)?.score > 0);
      mode = rankingMode;
    }
    $('catalog-result-note').textContent = `${visible.length} catalog experience${visible.length === 1 ? '' : 's'}${query ? mode === 'ai' ? ' · ordered by on-device AI similarity' : ' · keyword search' : ''}. Preferences and actual group availability are checked in your room.`;
    if (!visible.length) {
      const empty = node('div', undefined, 'empty-state');
      empty.append(node('h3', 'A little more room for possibility?'), node('p', 'Try another category, a flexible budget or fewer keywords. Optional AI searches meaning instead of exact words.'));
      container.append(empty); return;
    }
    visible.forEach((offer, index) => {
      const card = node('article', undefined, 'experience-card');
      const image = node('div', undefined, 'experience-art'); image.innerHTML = art(offer.domain, index);
      const tags = node('div', undefined, 'card-meta-tags');
      tags.append(node('span', offer.domain === 'movie' ? 'CINEMA NIGHT' : 'OUTDOOR ESCAPE', 'art-category'),
        node('span', `${offer.resources.filter((item) => item.state === 'FREE').length} places open`, 'card-capacity-pill'));
      image.append(tags, node('span', offer.domain === 'movie' ? 'A BIGGER KIND OF NIGHT.' : 'TAKE THE SCENIC ROUTE.', 'art-vibe-label'));
      const body = node('div', undefined, 'card-body');
      body.append(node('h3', offer.title), node('p', offer.description, 'card-desc'),
        node('p', new Date(offer.scheduleTime).toLocaleString(undefined, {weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'}), 'card-schedule'));
      const pricing = node('div', undefined, 'card-pricing-row');
      const amount = node('div'); amount.append(node('strong', price(offer.priceMinor), 'card-price-val'), node('small', offer.domain === 'movie' ? 'per person' : 'fixed group total', 'card-price-secondary'));
      pricing.append(amount, node('span', 'Fictional experience', 'card-price-label')); body.append(pricing);
      if (offer.domain === 'excursion') {
        const people = Number($('scout-people').value || 3), base = Math.floor(offer.priceMinor / people), remainder = offer.priceMinor % people;
        body.append(node('p', `For ${people}: ${Array.from({length: people}, (_, i) => price(base + Number(i < remainder))).join(' + ')}`, 'fine'));
      }
      const action = node('button', 'Plan this together ↗', 'btn btn-outline'); action.type = 'button';
      action.addEventListener('click', () => onPlan(offer.id)); body.append(action);
      if (query && mode === 'ai') body.append(node('p', '✦ On-device AI vibe match · not a budget or consensus score', 'ai-result-tag'));
      card.append(image, body); container.append(card);
    });
  }
  async function search() {
    const token = ++sequence;
    query = $('scout-query').value.trim();
    if (!query) { scores = null; render(); return; }
    if (query.length > 1000) { $('scout-status').textContent = 'Use a description under 1000 characters.'; return; }
    $('scout-status').textContent = scout.isReady() ? 'Finding the meaning in your description, on this device…' : 'Searching catalog keywords. Enable AI for meaning-based discovery.';
    try {
      const ranked = scout.isReady() ? await scout.rank(query, offers) : root.GroupPayAI.keywordRank(query, offers);
      if (token !== sequence) return;
      scores = ranked; rankingMode = scout.isReady() ? 'ai' : 'basic'; render();
      $('scout-status').textContent = rankingMode === 'ai' ? 'Ranked on your device. AI helps with the vibe; the room verifies the group fit.' : 'Keyword results. Optional AI understands descriptions beyond exact words.';
    } catch (error) {
      if (token !== sequence) return;
      scores = root.GroupPayAI.keywordRank(query, offers); rankingMode = 'basic'; render();
      $('scout-status').textContent = `${error.message} Showing keyword results.`;
    }
  }
  function init(options) {
    onPlan = options.onPlan;
    scout = root.GroupPayAI.create({onStatus(message, state) {
      $('scout-status').textContent = message;
      $('scout-enable').textContent = state === 'loading' ? 'Loading AI assets…' : state === 'ready' ? 'AI ready · turn off' : 'Enable on-device AI';
    }});
    $('scout-form').addEventListener('submit', (event) => { event.preventDefault(); search(); });
    $('scout-enable').addEventListener('click', async () => {
      if (loading) return;
      if (scout.isReady()) { sequence++; scout.disable(); rankingMode = 'basic'; scores = query ? root.GroupPayAI.keywordRank(query, offers) : null; render(); return; }
      loading = true; $('scout-enable').disabled = true;
      try { await scout.enable(); if (query) await search(); }
      catch (error) { $('scout-status').textContent = error.message; }
      finally { loading = false; $('scout-enable').disabled = false; }
    });
    $('scout-clear').addEventListener('click', () => { sequence++; query = ''; scores = null; $('scout-query').value = ''; render(); $('scout-status').textContent = scout.isReady() ? 'On-device AI ready. Describe a new vibe.' : 'Basic search is ready. Enable AI if you want meaning-based discovery.'; });
    for (const id of ['scout-people', 'scout-budget']) $(id).addEventListener('change', () => render());
    document.querySelectorAll('[data-vibe]').forEach((control) => control.addEventListener('click', () => { $('scout-query').value = control.dataset.vibe; search(); }));
  }
  root.GroupPayDiscover = {init, render, rankVerified: (query, options) => scout.rank(query, options), aiReady: () => !!scout?.isReady()};
})(window);
