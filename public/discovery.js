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
  const stopWords = new Set(['a', 'an', 'the', 'i', 'we', 'our', 'my', 'would', 'like', 'want', 'something', 'for', 'with', 'and', 'or', 'to', 'of', 'in', 'at', 'is', 'it']);
  let offers = [], filter = 'all', query = '', onPlan;
  function searchTerms(value) {
    return [...new Set(String(value || '').toLocaleLowerCase().match(/[a-z0-9]+/g) || [])]
      .filter((word) => !stopWords.has(word));
  }
  function searchText(offer) {
    let genre = '';
    if (typeof offer.meta === 'object' && offer.meta) genre = offer.meta.genre || '';
    else if (typeof offer.meta === 'string') {
      try { genre = JSON.parse(offer.meta).genre || ''; } catch {}
    }
    return [offer.title, offer.description, offer.domain, genre].filter(Boolean).join(' ').toLocaleLowerCase();
  }
  function art(domain, index) {
    const palettes = [['#24325d', '#7883ba', '#d2c0ab'], ['#845c79', '#bf879b', '#f3d3a6'], ['#367270', '#94b49f', '#e8d9ad']];
    const [bg, hill, sun] = palettes[index % palettes.length];
    const shape = domain === 'movie'
      ? `<circle cx="190" cy="77" r="40" fill="${sun}"/><ellipse cx="190" cy="77" rx="85" ry="19" fill="none" stroke="${hill}" stroke-width="8" transform="rotate(-22 190 77)"/><circle cx="80" cy="45" r="2" fill="#fff9"/><circle cx="280" cy="40" r="2" fill="#fff9"/><circle cx="320" cy="110" r="3" fill="#fff9"/><path d="M0 175L100 124L170 154L270 105L360 172V200H0Z" fill="${hill}" opacity=".55"/>`
      : `<circle cx="265" cy="62" r="36" fill="${sun}"/><path d="M0 145L100 40L178 130L255 75L360 163V200H0Z" fill="${hill}"/><path d="M0 190L100 109L180 169L280 120L360 176V200H0Z" fill="#1d4f5066"/><path d="M190 150Q140 173 220 200H310Q200 165 225 150Z" fill="#d7e4e8"/><path d="M57 151V80M35 120L57 83L80 120M29 139L57 102L84 139" stroke="#234e4b" fill="#234e4b" stroke-width="3"/>`;
    return `<svg viewBox="0 0 360 200" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><rect width="360" height="200" fill="${bg}"/>${shape}</svg>`;
  }
  function candidates() {
    const people = Number($('catalog-people').value || 3), raw = $('catalog-budget').value;
    if (![2, 3, 4].includes(people)) throw new Error('Choose 2–4 people.');
    if (raw !== '' && !/^\d+(\.\d{1,2})?$/.test(raw)) throw new Error('Use a nonnegative budget with at most two decimal places.');
    const ceiling = raw === '' ? null : Math.round(Number(raw) * 100);
    if (ceiling !== null && !Number.isSafeInteger(ceiling)) throw new Error('Budget is too large.');
    const words = searchTerms(query);
    return offers.filter((offer) => (offer.availability ? offer.availability.status !== 'past' : Date.parse(offer.scheduleTime) > Date.now()) &&
      (filter === 'all' || offer.domain === filter) &&
      (ceiling === null || (offer.domain === 'movie' ? offer.priceMinor : Math.ceil(offer.priceMinor / people)) <= ceiling) &&
      words.every((word) => searchText(offer).includes(word)));
  }
  function render(newFilter, newOffers) {
    if (newFilter) filter = newFilter;
    if (newOffers) offers = newOffers;
    const container = $('catalog-offers-grid'); container.replaceChildren();
    let visible;
    try { visible = candidates(); } catch (error) { $('catalog-result-note').textContent = error.message; return; }
    $('catalog-result-note').textContent = `${visible.length} upcoming experience${visible.length === 1 ? '' : 's'}${query ? ' matching your search' : ''}.`;
    if (!visible.length) {
      const empty = node('div', undefined, 'empty-state');
      const upcoming = offers.some((offer) => offer.availability ? offer.availability.status !== 'past' : Date.parse(offer.scheduleTime) > Date.now());
      empty.append(node('h3', !upcoming ? 'No upcoming sessions yet.' : query ? 'No experiences match that search.' : 'No experiences match these filters.'),
        node('p', !upcoming ? 'Ask the organizer to add future dates. Your saved groups and bookings are still available.' :
          'Try fewer search words, a different category or a higher budget. The catalog and your saved preferences are unchanged.'));
      container.append(empty); return;
    }
    visible.forEach((offer, index) => {
      const people = Number($('catalog-people').value || 3);
      const groupFits = !offer.availability || offer.availability.groupSizes.includes(people);
      const card = node('article', undefined, 'experience-card');
      const image = node('div', undefined, 'experience-art'); image.innerHTML = art(offer.domain, index);
      const tags = node('div', undefined, 'card-meta-tags');
      tags.append(node('span', offer.domain === 'movie' ? 'CINEMA NIGHT' : 'OUTDOOR ESCAPE', 'art-category'),
        node('span', groupFits ? `${offer.resources.filter((item) => item.state === 'FREE').length} places open` : `No group of ${people} available`, 'card-capacity-pill'));
      image.append(tags, node('span', offer.domain === 'movie' ? 'A BIGGER KIND OF NIGHT.' : 'TAKE THE SCENIC ROUTE.', 'art-vibe-label'));
      const body = node('div', undefined, 'card-body');
      body.append(node('h3', offer.title), node('p', offer.description, 'card-desc'),
        node('p', new Date(offer.scheduleTime).toLocaleString(undefined, {weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'}), 'card-schedule'));
      const pricing = node('div', undefined, 'card-pricing-row');
      const amount = node('div'); amount.append(node('strong', price(offer.priceMinor), 'card-price-val'), node('small', offer.domain === 'movie' ? 'per person' : 'fixed group total', 'card-price-secondary'));
      pricing.append(amount, node('span', 'Fictional experience', 'card-price-label')); body.append(pricing);
      if (offer.domain === 'excursion') {
        const people = Number($('catalog-people').value || 3), base = Math.floor(offer.priceMinor / people), remainder = offer.priceMinor % people;
        body.append(node('p', `For ${people}: ${Array.from({length: people}, (_, i) => price(base + Number(i < remainder))).join(' + ')}`, 'fine'));
      }
      const action = node('button', 'Plan this together ↗', 'btn btn-outline'); action.type = 'button';
      action.disabled = !groupFits;
      if (!groupFits) body.append(node('p', 'There are not enough adjacent seats or places for this group size. Try another session or group size.', 'fine'));
      action.addEventListener('click', () => onPlan(offer.id)); body.append(action);
      card.append(image, body); container.append(card);
    });
  }
  function search() {
    query = $('catalog-search-query').value.trim();
    if (query.length > 1000) { $('catalog-search-message').textContent = 'Use a description under 1000 characters.'; return; }
    render();
    $('catalog-search-message').textContent = query ? 'Showing catalog text matches. Your group room checks confirmed limits and capacity.' : 'Showing all upcoming experiences.';
  }
  function init(options) {
    onPlan = options.onPlan;
    $('catalog-search-form').addEventListener('submit', (event) => { event.preventDefault(); search(); });
    $('catalog-search-clear').addEventListener('click', () => { query = ''; $('catalog-search-query').value = ''; render(); $('catalog-search-message').textContent = 'Showing all upcoming experiences.'; });
    for (const id of ['catalog-people', 'catalog-budget']) $(id).addEventListener('change', () => render());
  }
  root.GroupPayDiscover = {init, render, searchTerms, searchText};
})(window);
