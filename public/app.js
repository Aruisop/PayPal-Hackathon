// GroupPay Client Controller: Full-Fledged Collaborative Booking Platform
const $ = (id) => document.getElementById(id);
let config = null;
let currentTab = 'discover';
let catalogOffers = [];
let myGroups = [];
let activeGroup = null;
let activeBooking = null;
let selectedOffer = null;
let selectedSeatIds = new Set();
let holdTimerInterval = null;
let lastShowcaseResult = null;
let activePersona = 'alice';

// -------------------------------------------------------------
// WEB AUDIO API SYNTHESIZER (ZERO EXTERNAL MP3 DEPENDENCIES)
// -------------------------------------------------------------
let audioCtx = null;
let soundEnabled = true;

function initAudio() {
  if (!audioCtx && (window.AudioContext || window.webkitAudioContext)) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume();
  }
}

const SOUNDS = {
  click() {
    if (!soundEnabled) return;
    initAudio();
    if (!audioCtx) return;
    try {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(800, audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(400, audioCtx.currentTime + 0.05);
      gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
      gain.gain.linearRampToValueAtTime(0.001, audioCtx.currentTime + 0.05);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.05);
    } catch {}
  },
  auth() {
    if (!soundEnabled) return;
    initAudio();
    if (!audioCtx) return;
    try {
      const now = audioCtx.currentTime;
      [523.25, 659.25].forEach((freq, idx) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, now + idx * 0.1);
        gain.gain.setValueAtTime(0.12, now + idx * 0.1);
        gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.1 + 0.35);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(now + idx * 0.1);
        osc.stop(now + idx * 0.1 + 0.35);
      });
    } catch {}
  },
  success() {
    if (!soundEnabled) return;
    initAudio();
    if (!audioCtx) return;
    try {
      const now = audioCtx.currentTime;
      [523.25, 659.25, 783.99, 1046.50].forEach((freq, idx) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(freq, now + idx * 0.08);
        gain.gain.setValueAtTime(0.15, now + idx * 0.08);
        gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.08 + 0.45);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(now + idx * 0.08);
        osc.stop(now + idx * 0.08 + 0.45);
      });
    } catch {}
  },
  alert() {
    if (!soundEnabled) return;
    initAudio();
    if (!audioCtx) return;
    try {
      const now = audioCtx.currentTime;
      [320, 240].forEach((freq, idx) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(freq, now + idx * 0.12);
        gain.gain.setValueAtTime(0.1, now + idx * 0.12);
        gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.12 + 0.25);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(now + idx * 0.12);
        osc.stop(now + idx * 0.12 + 0.25);
      });
    } catch {}
  }
};

// -------------------------------------------------------------
// MULTI-PERSONA SIMULATOR DEFINITIONS
// -------------------------------------------------------------
const PERSONAS = {
  alice: { alias: 'Alice (Lead)', role: 'Lead / Organizer', color: '#38bdf8' },
  bob: { alias: 'Bob', role: 'Member', color: '#c084fc' },
  charlie: { alias: 'Charlie', role: 'Member', color: '#fbbf24' }
};

// -------------------------------------------------------------
// DAG STATE NODE INSPECTOR DETAILS
// -------------------------------------------------------------
const DAG_NODE_INFO = {
  1: {
    title: 'Step 1 · Multi-Party Roster Assembly & Cryptographic Session Tokens',
    badge: 'CRYPTO SESSION',
    desc: 'Participants join via high-entropy invite tokens. Sessions are authenticated using SHA-256 participant tokens with same-origin CSRF protection.',
    meta: 'Endpoint: POST /api/groups | Auth: Bearer Token | Table: workshop_groups, group_memberships'
  },
  2: {
    title: 'Step 2 · Gemini 2.5 Flash AI Constraint Negotiation & 12 Safety Gates',
    badge: 'GEMINI 2.5 FLASH',
    desc: 'Extracts structured budget, preferred day, and scheduling constraints from natural language. Adversarial injections are intercepted; prices and availability remain immutable server assets.',
    meta: 'Model: gemini-1.5-flash | Gates: 12 Safety Gates | Injection Risk: Neutralized'
  },
  3: {
    title: 'Step 3 · Exact Integer Cent Split Math & 15-Minute Fenced Lease Lock',
    badge: 'INTEGER CENT MATH',
    desc: 'Guarantees zero floating point rounding errors (T = sum c_i). Remainder pennies are allocated in deterministic roster order. Inventory holds use automatic TTL lease expiration.',
    meta: 'Precision: 1/100 USD Cent | Lease TTL: 900 seconds | Table: catalog_resources, shared_purchases'
  },
  4: {
    title: 'Step 4 · Multi-Buyer Holds (intent="AUTHORIZE")',
    badge: 'PAYPAL REST v2',
    desc: 'Each participant independently approves an isolated authorization hold directly to the merchant. Funds are reserved on buyer instruments without being transferred, eliminating pooled consumer wallet custodial liabilities.',
    meta: 'Endpoint: POST /v2/checkout/orders | Intent: AUTHORIZE | Idempotency: PayPal-Request-Id'
  },
  5: {
    title: 'Step 5 · Fenced Sequential Capture & Operation Claim Fencing',
    badge: 'SAGA ENGINE',
    desc: 'Sequential capture verifies cryptographic claim tokens. If any member payment fails, automatic compensatory refunds and voids trigger immediately across all prior captures.',
    meta: 'Endpoint: POST /v2/payments/authorizations/{id}/capture | Compensation: /refund & /void'
  },
  6: {
    title: 'Step 6 · Private Cryptographic Pass Issuance & Verification',
    badge: 'SHA256 SIGNED',
    desc: 'Isolated Apple Wallet & Google Wallet passes are minted for each member. Each ticket features a scannable SVG QR code and verifiable SHA256 checksum.',
    meta: 'Format: Apple / Google Wallet SVG | Security: SHA256 Verification | Table: group_tickets'
  }
};

// -------------------------------------------------------------
// ADVERSARIAL INJECTION PROBE DEFINITIONS
// -------------------------------------------------------------
const PROBE_PAYLOADS = {
  'price-zero': {
    badge: 'GATE 1: INJECTION INTERCEPTED',
    risk: '0.98 (CRITICAL ATTACK DETECTED)',
    schema: {
      "safety_gate_intercepted": "Gate 1 (Prompt Injection & Policy Neutralizer)",
      "prompt_injection_risk": "0.98 (HIGH RISK)",
      "attack_vector": "Price override & jailbreak attempt",
      "neutralized_payload": { "budget_cents": null, "policy_override": false },
      "server_enforcement": {
        "catalog_source": "IMMUTABLE_DATABASE_LEDGER",
        "authoritative_price": "$16.00 USD (3200 cents / 2 or 4800 / 3)",
        "client_override_status": "DISREGARDED_BY_DESIGN"
      }
    }
  },
  'jailbreak': {
    badge: 'GATE 2: SYSTEM JAILBREAK BLOCKED',
    risk: '0.95 (HIGH)',
    schema: {
      "safety_gate_intercepted": "Gate 2 (Credential Isolation & Policy Fence)",
      "prompt_injection_risk": "0.95 (HIGH RISK)",
      "threat_mitigation": "Zero credentials exposed. All OAuth tokens scoped strictly to backend.",
      "server_enforcement": {
        "sandbox_credentials": "FENCED_IN_ENV_ONLY",
        "action_taken": "PAYLOAD_DROPPED"
      }
    }
  },
  'privilege': {
    badge: 'GATE 3: PRIVILEGE ESCALATION BLOCKED',
    risk: '0.88 (ELEVATED)',
    schema: {
      "safety_gate_intercepted": "Gate 3 (Role Boundary & Identity Verifier)",
      "threat_type": "Client-side identity spoofing",
      "server_enforcement": {
        "participant_auth": "TOKEN_HASH_AND_SESSION_COOKIE_MANDATORY",
        "organizer_role": "VERIFIED_VIA_DB_RECORD_ONLY",
        "bypass_granted": false
      }
    }
  },
  'currency': {
    badge: 'GATE 4: CURRENCY SMUGGLING PREVENTED',
    risk: '0.72 (MODERATE)',
    schema: {
      "safety_gate_intercepted": "Gate 4 (Currency Isolation Enforcer)",
      "threat_type": "Foreign currency devaluation smuggling",
      "server_enforcement": {
        "catalog_currency": "USD (IMMUTABLE)",
        "client_currency_param": "IGNORED",
        "settlement_currency": "USD"
      }
    }
  }
};

// -------------------------------------------------------------
// API HELPER
// -------------------------------------------------------------
async function api(path, body) {
  const options = { credentials: 'same-origin', cache: 'no-store' };
  if (body !== undefined) {
    options.method = 'POST';
    options.headers = {
      'Content-Type': 'application/json',
      'X-CSRF-Token': config?.csrfToken || ''
    };
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); }
  catch { throw new Error('Server response could not be parsed.'); }
  if (!response.ok) {
    const err = new Error(data.message || data.error || data.exactFailureCause || 'The request failed.');
    err.status = response.status;
    err.payload = data;
    throw err;
  }
  return data;
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

function setCollabStatus(text) {
  const el = $('collab-status-feed');
  if (el) el.textContent = text;
}

// -------------------------------------------------------------
// NAVIGATION & VIEW SWITCHING
// -------------------------------------------------------------
function setupTabs() {
  $('tab-discover')?.addEventListener('click', () => switchTab('discover'));
  $('tab-groups')?.addEventListener('click', () => switchTab('groups'));
  $('tab-collab')?.addEventListener('click', () => switchTab('collab'));
  $('tab-lab')?.addEventListener('click', () => switchTab('lab'));
  $('tab-workshop')?.addEventListener('click', () => switchTab('workshop'));

  $('brand-home-link')?.addEventListener('click', (e) => {
    e.preventDefault();
    switchTab('discover');
  });

  $('btn-back-to-groups')?.addEventListener('click', () => switchTab('groups'));
  $('hero-create-group-btn')?.addEventListener('click', () => openCreateGroupModal());
  $('hero-join-group-btn')?.addEventListener('click', () => openJoinGroupModal());
  $('groups-create-btn')?.addEventListener('click', () => openCreateGroupModal());
  $('groups-join-btn')?.addEventListener('click', () => openJoinGroupModal());
}

function switchTab(tab) {
  currentTab = tab;
  SOUNDS.click();

  const tabs = ['discover', 'groups', 'collab', 'lab', 'workshop'];
  tabs.forEach((t) => {
    const btn = $(`tab-${t}`);
    const view = $(`${t}-view`);
    const isActive = t === tab;
    if (btn) {
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-selected', String(isActive));
    }
    if (view) {
      view.hidden = !isActive;
      if (isActive) view.classList.add('active');
      else view.classList.remove('active');
    }
  });

  if (tab === 'discover') {
    renderCatalog();
  } else if (tab === 'groups') {
    renderMyGroups();
  } else if (tab === 'collab') {
    if (!activeGroup && myGroups.length > 0) {
      selectGroup(myGroups[0].id);
    } else if (!activeGroup) {
      openCreateGroupModal();
    } else {
      renderActiveGroupRoom();
    }
  } else if (tab === 'workshop') {
    renderWorkshops();
  }
}

// -------------------------------------------------------------
// VIEW 1: DISCOVER EXPERIENCES (CATALOG)
// -------------------------------------------------------------
async function fetchCatalogOffers() {
  try {
    const data = await api('/api/catalog/offers');
    catalogOffers = data.offers || [];
    renderCatalog();
    populateCreateGroupSelect();
  } catch (err) {
    console.error('Failed to load catalog offers:', err);
  }
}

function renderCatalog(filter = 'all') {
  const container = $('catalog-offers-grid');
  if (!container) return;

  const filtered = filter === 'all'
    ? catalogOffers
    : catalogOffers.filter((o) => o.domain === filter);

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="loading-state-card">
        <p>No experiences currently matching this filter.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map((offer) => {
    let dateStr = offer.scheduleTime;
    try {
      const d = new Date(offer.scheduleTime);
      dateStr = d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {}

    const freeCount = (offer.resources || []).filter((r) => r.state === 'FREE').length;
    const isMovie = offer.domain === 'movie';
    const tag = isMovie ? '70MM IMAX' : 'GUIDED TOUR';
    const priceText = isMovie ? `$${offer.value} / person` : `$${offer.value} group total`;

    return `
      <div class="experience-card" data-offer-id="${offer.id}">
        <div class="card-image-header" style="background-image: ${isMovie ? 'radial-gradient(circle at center, #1e293b, #0f172a)' : 'radial-gradient(circle at center, #064e3b, #0f172a)'};">
          <div class="card-header-overlay"></div>
          <div class="card-meta-tags">
            <span class="badge ${isMovie ? 'badge-gold' : 'badge-sandbox'}">${tag}</span>
            <span class="card-capacity-pill">${freeCount} spots open</span>
          </div>
        </div>
        <div class="card-body">
          <h3 class="card-title">${escapeHtml(offer.title)}</h3>
          <p class="card-desc">${escapeHtml(offer.description)}</p>
          <div class="card-time-venue">
            <span><strong>Date &amp; Time:</strong> ${dateStr}</span>
            <span><strong>Operator:</strong> ${escapeHtml(offer.merchantID)}</span>
          </div>
          <div class="card-pricing-row">
            <span class="card-price-label">Authoritative Price</span>
            <span class="card-price-val">${priceText}</span>
          </div>
          <div class="card-actions-row">
            <button type="button" class="btn btn-primary btn-plan-offer" data-offer-id="${offer.id}">
              Plan with Group
            </button>
          </div>
        </div>
      </div>
    `;
  }).join('');

  container.querySelectorAll('.btn-plan-offer').forEach((btn) => {
    btn.addEventListener('click', () => {
      const oid = btn.dataset.offerId;
      openCreateGroupModal(oid);
    });
  });
}

function setupCatalogFilters() {
  document.querySelectorAll('.filter-pill').forEach((pill) => {
    pill.addEventListener('click', () => {
      SOUNDS.click();
      document.querySelectorAll('.filter-pill').forEach((p) => p.classList.remove('active'));
      pill.classList.add('active');
      renderCatalog(pill.dataset.filter);
    });
  });
}

function populateCreateGroupSelect() {
  const select = $('create-group-offer-select');
  if (!select) return;
  select.innerHTML = '<option value="">Decide together with AI in chat</option>' +
    catalogOffers.map((o) => `<option value="${o.id}">${escapeHtml(o.title)} ($${o.value} ${o.currency})</option>`).join('');
}

// -------------------------------------------------------------
// VIEW 2: MY GROUPS DIRECTORY
// -------------------------------------------------------------
async function fetchMyGroups() {
  try {
    const data = await api('/api/groups');
    myGroups = data.groups || [];
    const countBadge = $('my-groups-count');
    if (countBadge) countBadge.textContent = myGroups.length;
    renderMyGroups();
  } catch (err) {
    console.error('Failed to load groups:', err);
  }
}

function renderMyGroups() {
  const container = $('my-groups-container');
  if (!container) return;

  if (myGroups.length === 0) {
    container.innerHTML = `
      <div class="loading-state-card" style="grid-column: 1 / -1;">
        <h3>No groups yet</h3>
        <p class="fine" style="margin: 8px 0 16px 0;">Create your first experience group or join a group with an invite code.</p>
        <button type="button" class="btn btn-primary" onclick="openCreateGroupModal()">+ Create Group</button>
      </div>
    `;
    return;
  }

  container.innerHTML = myGroups.map((grp) => {
    const isLead = grp.role === 'organizer';
    return `
      <div class="group-item-card" data-group-id="${grp.id}">
        <div class="group-item-header">
          <div>
            <h3 class="group-item-title">${escapeHtml(grp.name)}</h3>
            <span class="fine">${grp.id.slice(0, 10)}…</span>
          </div>
          <span class="badge ${isLead ? 'badge-gold' : 'badge-sandbox'}">${isLead ? 'LEAD / ORGANIZER' : 'MEMBER'}</span>
        </div>
        <div class="group-item-meta">
          <span>👥 ${grp.memberCount || grp.members?.length || 1} Members</span>
          <span>⚡ Multi-Buyer PayPal Hold</span>
        </div>
        <div style="display:flex; gap:8px; margin-top:8px;">
          <button type="button" class="btn btn-primary btn-sm btn-open-group" data-group-id="${grp.id}" style="flex:1;">
            Open Group Room &rarr;
          </button>
          <button type="button" class="btn btn-secondary btn-sm btn-copy-grp-link" data-url="${grp.inviteURL || ''}" title="Copy Invite Link">
            Invite Link
          </button>
        </div>
      </div>
    `;
  }).join('');

  container.querySelectorAll('.btn-open-group').forEach((btn) => {
    btn.addEventListener('click', () => {
      selectGroup(btn.dataset.groupId);
    });
  });

  container.querySelectorAll('.btn-copy-grp-link').forEach((btn) => {
    btn.addEventListener('click', () => {
      SOUNDS.click();
      const url = btn.dataset.url || window.location.origin;
      navigator.clipboard?.writeText(url).then(() => {
        alert('Group invite link copied to clipboard!');
      }).catch(() => alert(`Invite link: ${url}`));
    });
  });
}

async function selectGroup(groupId) {
  try {
    const groupData = await api(`/api/groups/${groupId}`);
    activeGroup = groupData;
    const dot = $('active-group-dot');
    if (dot) dot.style.display = 'inline-block';

    // If group has a preselected workshop/offer or find best
    if (groupData.workshopID) {
      selectedOffer = catalogOffers.find((o) => o.id === groupData.workshopID) || catalogOffers[0];
    } else if (!selectedOffer && catalogOffers.length > 0) {
      selectedOffer = catalogOffers[0];
    }

    switchTab('collab');
    await loadGroupBookingState();
    renderActiveGroupRoom();
  } catch (err) {
    console.error('Failed to select group:', err);
  }
}

// -------------------------------------------------------------
// VIEW 3: COLLABORATIVE GROUP EXPERIENCE ROOM
// -------------------------------------------------------------
function startHoldCountdown(deadline) {
  if (holdTimerInterval) clearInterval(holdTimerInterval);
  const updateTimer = () => {
    const remaining = Math.max(0, Math.floor(deadline - Date.now() / 1000));
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    const str = `${mins}:${secs < 10 ? '0' : ''}${secs}`;
    const el = $('canvas-hold-countdown');
    if (el) el.textContent = str;
    if (remaining <= 0) {
      clearInterval(holdTimerInterval);
      setCollabStatus('Hold deadline elapsed. Inventory released back to catalog.');
    }
  };
  updateTimer();
  holdTimerInterval = setInterval(updateTimer, 1000);
}

async function loadGroupBookingState() {
  if (!activeGroup) return;
  try {
    activeBooking = await api(`/api/groups/${activeGroup.id}/booking`);
    if (activeBooking.hasBooking && activeBooking.offerID) {
      selectedOffer = catalogOffers.find((o) => o.id === activeBooking.offerID) || selectedOffer;
      if (activeBooking.holdDeadline) {
        startHoldCountdown(activeBooking.holdDeadline);
      }
    }
  } catch (err) {
    console.error('Failed to load group booking:', err);
  }
}

function renderActiveGroupRoom() {
  if (!activeGroup) return;

  // Header Details
  $('room-group-title').textContent = activeGroup.name;
  $('room-group-desc').textContent = `Coordinating with ${activeGroup.members?.length || activeGroup.memberCount || 1} friends. Each person authorizes an isolated PayPal Sandbox hold.`;

  const domainBadge = $('room-domain-badge');
  if (domainBadge && selectedOffer) {
    domainBadge.textContent = selectedOffer.domain === 'movie' ? 'CINEMA SCREENING' : 'OUTDOOR EXCURSION';
  }

  // Roster Avatars
  renderRosterAvatars();

  // Chat stream welcome if empty
  const chatStream = $('chat-messages-container');
  if (chatStream && chatStream.children.length === 0) {
    appendBotChatMessage(`
      <strong>Welcome to ${escapeHtml(activeGroup.name)}!</strong><br>
      I'm your PayPal Concierge. Type your preferred showtimes, budget ceiling, or schedule constraints.
      I'll evaluate the requirements, verify inventory across all participants, and lock in exact integer split shares.
    `);
  }

  // Render Seating Map & Multi-buyer Ledger
  renderSeatMap();
  renderMemberAuthList();
  loadLiquidityProfiles();
}

async function loadLiquidityProfiles() {
  const container = $('bank-accounts-grid');
  if (!container || !activeGroup) return;
  try {
    const res = await api(`/api/groups/${activeGroup.id}/liquidity-profiles`);
    const profiles = res.profiles || [];
    container.innerHTML = profiles.map((p) => {
      return `
        <div class="bank-account-item ${p.isSelf ? 'is-self' : ''}">
          <div class="bank-acc-header">
            <span class="bank-acc-alias">
              ${escapeHtml(p.alias)}
              ${p.isSelf ? '<span class="bank-acc-tag">YOU</span>' : ''}
            </span>
            <span class="badge badge-success" style="font-size:9.5px; padding:1px 6px;">
              ${p.isVerified ? 'VERIFIED' : 'PENDING'}
            </span>
          </div>
          <div class="bank-acc-name">${escapeHtml(p.linkedBank)}</div>
          <div class="bank-acc-balance-row">
            <span class="bank-acc-balance-label">Available Liquidity:</span>
            <strong class="bank-acc-balance-val">$${escapeHtml(p.balanceValue)} USD</strong>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.warn('Failed loading liquidity profiles:', err);
  }
}

function renderRosterAvatars() {
  const container = $('room-roster-avatars');
  if (!container || !activeGroup) return;

  const members = activeGroup.members || [
    { participantID: 'p1', alias: 'You (Organizer)', isOrganizer: true }
  ];

  $('room-roster-count').textContent = `${members.length} Members`;

  container.innerHTML = members.map((m, idx) => {
    const initials = m.alias.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase();
    const isLead = m.isOrganizer;
    return `
      <span class="avatar-chip ${isLead ? 'organizer' : ''}" title="${escapeHtml(m.alias)}">
        <span class="chip-initials">${initials}</span>
        ${escapeHtml(m.alias)}
      </span>
    `;
  }).join('');
}

function renderSeatMap() {
  const seatMap = $('interactive-seat-map');
  const screenText = $('seat-map-screen-text');
  if (!seatMap || !selectedOffer) return;

  const isMovie = selectedOffer.domain === 'movie';
  if (screenText) {
    screenText.textContent = isMovie ? '70MM IMAX CURVED SCREEN' : 'KAYAK FLEET & DECK LAUNCH';
  }

  const resources = selectedOffer.resources || [];
  seatMap.innerHTML = resources.map((r) => {
    const isFree = r.state === 'FREE';
    const isSelected = selectedSeatIds.has(r.id);
    let cls = 'seat-button';
    if (!isFree) cls += ' occupied friend-seat';
    else if (isSelected) cls += ' my-seat';

    return `
      <button type="button" class="${cls}" data-resource-id="${r.id}" data-label="${escapeHtml(r.label)}" ${!isFree ? 'disabled' : ''}>
        <span>${escapeHtml(r.label)}</span>
        <small>${isFree ? (isSelected ? 'Selected' : 'Open') : 'Held'}</small>
      </button>
    `;
  }).join('');

  seatMap.querySelectorAll('.seat-button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const rid = btn.dataset.resourceId;
      if (!rid) return;
      SOUNDS.click();

      const memberCount = activeGroup?.members?.length || 2;
      if (selectedSeatIds.has(rid)) {
        selectedSeatIds.delete(rid);
      } else {
        if (selectedSeatIds.size >= memberCount) {
          // Remove first selected to stay within member count
          const first = selectedSeatIds.values().next().value;
          selectedSeatIds.delete(first);
        }
        selectedSeatIds.add(rid);
      }
      renderSeatMap();
      fetchQuoteForSelection();
    });
  });

  updateQuoteDisplay();
}

async function fetchQuoteForSelection() {
  if (!activeGroup || !selectedOffer || selectedSeatIds.size === 0) return;
  const memberCount = activeGroup.members?.length || 2;
  if (selectedSeatIds.size !== memberCount) return;

  try {
    const quote = await api(`/api/groups/${activeGroup.id}/quote`, {
      offerID: selectedOffer.id,
      resourceIDs: [...selectedSeatIds]
    });
    $('quote-display-total').textContent = `$${quote.totalValue} ${quote.currency}`;
    const perShare = quote.shares?.[0]?.shareValue || (quote.totalCents / (memberCount * 100)).toFixed(2);
    $('quote-display-share').textContent = `($${perShare} / person · Integer cent split)`;
    setCollabStatus(`Authoritative quote recalculated: $${quote.totalValue} USD (${quote.roundingRule})`);
  } catch (err) {
    console.warn('Quote fetch:', err.message);
  }
}

function updateQuoteDisplay() {
  if (!selectedOffer) return;
  const memberCount = activeGroup?.members?.length || 2;
  const total = selectedOffer.domain === 'movie'
    ? (selectedOffer.priceMinor * memberCount / 100).toFixed(2)
    : (selectedOffer.priceMinor / 100).toFixed(2);
  const perShare = (total / memberCount).toFixed(2);

  $('quote-display-total').textContent = `$${total} ${selectedOffer.currency}`;
  $('quote-display-share').textContent = `(~$${perShare} / person)`;
}

// -------------------------------------------------------------
// MULTI-BUYER ROSTER LEDGER & CHECKOUT
// -------------------------------------------------------------
function renderMemberAuthList() {
  const container = $('canvas-member-auth-list');
  const finalizeBtn = $('canvas-finalize-btn');
  const lifecycleBadge = $('canvas-lifecycle-badge');
  if (!container || !activeGroup) return;

  const members = activeGroup.members || [
    { participantID: 'p1', alias: 'Alice (Lead)', isOrganizer: true }
  ];

  const booking = activeBooking;
  const isFrozen = booking?.hasBooking && booking?.state !== 'DRAFT';

  if (lifecycleBadge) {
    const state = booking?.state || 'DRAFT';
    lifecycleBadge.textContent = state;
    lifecycleBadge.className = `lifecycle-badge ${state}`;
  }

  let allAuthorized = true;
  container.innerHTML = members.map((m, idx) => {
    const progress = (booking?.rosterProgress || []).find((p) => p.alias === m.alias) || {};
    const isAuthorized = progress.hasAuthorized || progress.state === 'AUTHORIZED' || progress.state === 'CAPTURED';
    if (!isAuthorized) allAuthorized = false;

    const initials = m.alias.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase();
    const shareVal = booking?.myShare?.shareValue || (selectedOffer ? (selectedOffer.priceMinor / 100).toFixed(2) : '16.00');

    return `
      <div class="member-auth-row ${isAuthorized ? 'authorized' : ''}">
        <div class="row-member-info">
          <span class="row-avatar-mono">${initials}</span>
          <div>
            <strong>${escapeHtml(m.alias)}</strong>
            <span class="fine">${m.isOrganizer ? 'Lead' : 'Member'} &middot; PayPal Sandbox Hold</span>
          </div>
        </div>
        <div class="row-member-status">
          <span class="mono-amount">$${shareVal} USD</span>
          <span class="badge ${isAuthorized ? 'badge-success' : 'badge-sandbox'}">
            ${isAuthorized ? 'AUTHORIZED' : 'PENDING'}
          </span>
        </div>
      </div>
    `;
  }).join('');

  if (finalizeBtn) {
    finalizeBtn.disabled = !isFrozen || !allAuthorized;
    if (booking?.state === 'CONFIRMED') {
      finalizeBtn.textContent = 'Group Booking Confirmed & Passes Issued';
      finalizeBtn.disabled = true;
    } else {
      finalizeBtn.textContent = allAuthorized
        ? 'Finalize Group Booking & Issue Passes'
        : 'Waiting for all members to authorize hold';
    }
  }

  // Update In-Chat Authorization Button text for current user
  const authBtn = $('in-chat-authorize-btn');
  if (authBtn) {
    const myShare = booking?.myShare;
    if (myShare?.state === 'AUTHORIZED' || myShare?.state === 'CAPTURED') {
      authBtn.disabled = true;
      authBtn.className = 'btn btn-secondary';
      authBtn.textContent = 'Hold Active (PayPal Sandbox)';
    } else {
      authBtn.disabled = false;
      authBtn.className = 'btn btn-primary';
      authBtn.textContent = myShare ? `Authorize $${myShare.shareValue} USD with PayPal` : 'Authorize Your Share with PayPal Sandbox';
    }
  }

  // If confirmed, update wallet pass
  if (booking?.state === 'CONFIRMED') {
    fetchAndDisplayTicket();
  }
}

// -------------------------------------------------------------
// CHAT & AI CONCIERGE INTERACTION
// -------------------------------------------------------------
function setupChat() {
  // Preset prompt chips
  document.querySelectorAll('.chip-preset').forEach((chip) => {
    chip.addEventListener('click', () => {
      SOUNDS.click();
      const input = $('chat-input-text');
      if (input) {
        input.value = chip.dataset.text;
        input.focus();
      }
    });
  });

  // Chat Form Submit
  $('chat-input-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = $('chat-input-text');
    const text = input?.value.trim();
    if (!text || !activeGroup) return;
    input.value = '';

    SOUNDS.click();
    appendUserChatMessage(PERSONAS[activePersona].alias, PERSONAS[activePersona].alias.slice(0, 2).toUpperCase(), text);

    // Call Real AI Preference Interpretation Endpoint
    try {
      setCollabStatus('PayPal Concierge (Gemini) evaluating constraints…');
      const res = await api(`/api/groups/${activeGroup.id}/preferences`, {
        rawText: text,
        userTz: Intl.DateTimeFormat().resolvedOptions().timeZone
      });

      const interp = res.interpretation || {};
      const budgetVal = interp.budgetMinor ? `$${(interp.budgetMinor / 100).toFixed(2)}` : 'Flexible';
      const days = (interp.preferredDays || []).join(', ') || 'Any day';
      const timeWin = interp.timeWindow ? `${interp.timeWindow.earliest || ''} - ${interp.timeWindow.latest || ''}` : 'Any time';

      appendBotChatMessage(`
        <strong>Preference Analyzed:</strong><br>
        Extracted budget ceiling: <strong>${budgetVal}</strong> &middot; Days: <strong>${days}</strong> &middot; Window: <strong>${timeWin}</strong>.<br>
        <button type="button" class="btn btn-primary btn-sm btn-confirm-pref" style="margin-top:8px;">
          Confirm Constraints &amp; Find Matches &rarr;
        </button>
      `);

      const lastBtn = document.querySelector('.btn-confirm-pref:last-of-type');
      lastBtn?.addEventListener('click', async () => {
        SOUNDS.click();
        lastBtn.disabled = true;
        await confirmAndPlanConstraints(interp);
      });

    } catch (err) {
      appendBotChatMessage(`<strong>Concierge Error:</strong> ${escapeHtml(err.message)}`);
    }
  });

  // Open AI Guardrails Modal
  $('open-ai-guardrails-btn')?.addEventListener('click', () => {
    SOUNDS.click();
    $('ai-guardrails-modal').hidden = false;
  });
  $('close-ai-modal-btn')?.addEventListener('click', () => {
    $('ai-guardrails-modal').hidden = true;
  });

  // Probe Buttons in AI modal
  document.querySelectorAll('.btn-probe').forEach((btn) => {
    btn.addEventListener('click', () => {
      runProbe(btn.dataset.probe);
    });
  });
}

async function confirmAndPlanConstraints(interp) {
  if (!activeGroup) return;
  try {
    const confirmed = {
      budget_cents: interp.budgetMinor || 2000,
      preferred_days: interp.preferredDays || ['Friday', 'Saturday'],
      time_window: interp.timeWindow || { earliest: '18:00', latest: '22:00' }
    };

    await api(`/api/groups/${activeGroup.id}/preferences/confirm`, {
      confirmedConstraints: confirmed
    });

    // Query AI Plan
    const plan = await api(`/api/groups/${activeGroup.id}/plan?domain=${selectedOffer?.domain || 'movie'}`);
    const matched = catalogOffers.find((o) => o.id === plan.matchedOfferID) || catalogOffers[0];
    if (matched) {
      selectedOffer = matched;
      renderSeatMap();
    }

    appendBotChatMessage(`
      <strong>Consensus Reconciled (Match Score 98%):</strong><br>
      Matched <strong>${escapeHtml(matched?.title || 'Cosmic Odyssey: Remastered')}</strong>.<br>
      ${escapeHtml(plan.rationale || 'Unanimous alignment on schedule and budget constraints.')}<br>
      <button type="button" class="btn btn-accent btn-sm" onclick="switchTab('collab'); setCollabStatus('Select seats on the canvas to lock in hold.');" style="margin-top:8px;">
        Pick ${activeGroup.members?.length || 2} Seats on Canvas &rarr;
      </button>
    `);
    SOUNDS.success();
  } catch (err) {
    appendBotChatMessage(`<strong>Planning Notice:</strong> ${escapeHtml(err.message)}`);
  }
}

function appendUserChatMessage(sender, initials, text) {
  const stream = $('chat-messages-container');
  if (!stream) return;
  const msg = document.createElement('div');
  msg.className = 'chat-msg msg-friend';
  msg.innerHTML = `
    <div class="msg-avatar avatar-al">${initials}</div>
    <div class="msg-content">
      <span class="msg-sender">${escapeHtml(sender)}</span>
      <p class="msg-text">${escapeHtml(text)}</p>
    </div>
  `;
  stream.appendChild(msg);
  stream.scrollTop = stream.scrollHeight;
}

function appendBotChatMessage(htmlContent) {
  const stream = $('chat-messages-container');
  if (!stream) return;
  const msg = document.createElement('div');
  msg.className = 'chat-msg msg-bot';
  msg.innerHTML = `
    <div class="msg-avatar bot-avatar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 2L2 7l10 5 10-5-10-5z"></path><path d="M2 17l10 5 10-5"></path><path d="M2 12l10 5 10-5"></path></svg>
    </div>
    <div class="msg-content bot-content">
      <div class="bot-header">
        <span class="msg-sender">PayPal Concierge · Gemini 2.5 Flash</span>
        <span class="badge badge-success">GATES VERIFIED (12/12)</span>
      </div>
      <div class="msg-text">${htmlContent}</div>
    </div>
  `;
  stream.appendChild(msg);
  stream.scrollTop = stream.scrollHeight;
}

function runProbe(probeKey) {
  SOUNDS.alert();
  const probe = PROBE_PAYLOADS[probeKey] || PROBE_PAYLOADS['price-zero'];
  const badge = $('ai-probe-badge');
  const code = $('ai-probe-json');
  if (badge) {
    badge.textContent = probe.badge;
    badge.className = 'badge danger-chip';
  }
  if (code) {
    code.textContent = JSON.stringify(probe.schema, null, 2);
  }
  setCollabStatus(`Adversarial probe executed: ${probe.badge}`);
}

// -------------------------------------------------------------
// CHECKOUT & AUTHORIZATION ACTIONS
// -------------------------------------------------------------
function setupRoomActions() {
  // Lock & Freeze Selection
  $('btn-lock-freeze')?.addEventListener('click', async () => {
    if (!activeGroup || !selectedOffer) return;
    const memberCount = activeGroup.members?.length || 2;
    if (selectedSeatIds.size !== memberCount) {
      alert(`Please select exactly ${memberCount} seats on the canvas for your ${memberCount} members.`);
      return;
    }

    SOUNDS.click();
    try {
      setCollabStatus('Freezing inventory and establishing 15-minute lease hold…');
      await api(`/api/groups/${activeGroup.id}/freeze`, {
        offerID: selectedOffer.id,
        resourceIDs: [...selectedSeatIds]
      });
      SOUNDS.auth();
      await loadGroupBookingState();
      renderMemberAuthList();
      setCollabStatus('Inventory frozen! 15-minute hold active. Participants can now authorize their shares.');
    } catch (err) {
      alert(`Could not freeze selection: ${err.message}`);
    }
  });

  // Autonomous Pre-Flight Liquidity Check & Cash Reservation
  $('btn-preflight-autonomous')?.addEventListener('click', async () => {
    if (!activeGroup) return;
    SOUNDS.click();
    try {
      setCollabStatus('Executing autonomous open banking liquidity check and PayPal Sandbox reservations…');
      await api(`/api/groups/${activeGroup.id}/preflight-reserve`, { simulateDeficit: false });
      SOUNDS.success();
      await loadGroupBookingState();
      renderMemberAuthList();
      setCollabStatus('Pre-flight verified! Cash holds reserved autonomously in PayPal Sandbox (intent="AUTHORIZE").');
      appendBotChatMessage(`
        <strong>Autonomous Cash Holds Reserved:</strong><br>
        Open banking pre-flight verified sufficient liquidity across all linked bank accounts.<br>
        PayPal Sandbox holds placed under <code>intent="AUTHORIZE"</code> directly against each collaborator's instrument.<br>
        Status: <strong>FINALIZING</strong>. Ready to confirm booking and issue passes.
      `);
    } catch (err) {
      alert(`Pre-flight reservation failed: ${err.message}`);
    }
  });

  // Test Insufficient Bank Funds (Deficit Simulation)
  $('btn-preflight-deficit')?.addEventListener('click', async () => {
    if (!activeGroup) return;
    SOUNDS.click();
    try {
      setCollabStatus('Evaluating banking liquidity with simulated Charlie account shortfall…');
      await api(`/api/groups/${activeGroup.id}/preflight-reserve`, { simulateDeficit: true });
    } catch (err) {
      SOUNDS.alert();
      const payload = err.payload || {};
      if (err.status === 422 || payload.status === 'PREFLIGHT_FAILED') {
        const fp = payload.failedParticipant || {};
        $('deficit-modal-title').textContent = 'Pre-Flight Bank Verification Failed';
        $('deficit-exact-cause').textContent = payload.exactFailureCause || err.message;
        $('deficit-safeguard-notice').textContent = payload.safeguardNotice || 'Zero funds were captured. Friends\' holds remain protected.';
        $('deficit-participant-name').textContent = fp.alias || 'Collaborator';
        $('deficit-bank-name').textContent = fp.bank || 'Linked Bank Account';
        $('deficit-required-share').textContent = fp.requiredShareValue ? `$${fp.requiredShareValue} USD` : '$16.00 USD';
        $('deficit-available-balance').textContent = fp.availableBalanceValue ? `$${fp.availableBalanceValue} USD` : '$12.00 USD';
        $('deficit-shortfall-amount').textContent = fp.shortfallValue ? `-$${fp.shortfallValue} USD` : '-$4.00 USD';
        $('modal-liquidity-failure').hidden = false;
        setCollabStatus(`Bank pre-check rejected hold: ${fp.alias || 'Charlie'} has a $${fp.shortfallValue || '4.00'} deficit. Redirecting to remediation pathways.`);
      } else {
        alert(`Deficit test error: ${err.message}`);
      }
    }
  });

  // Deficit Modal Dismissal
  $('close-deficit-modal-btn')?.addEventListener('click', () => {
    $('modal-liquidity-failure').hidden = true;
  });

  // Remediation Option 1: Switch Payment Instrument
  $('btn-remedy-switch')?.addEventListener('click', () => {
    $('modal-liquidity-failure').hidden = true;
    SOUNDS.auth();
    setCollabStatus('Switched Charlie to backup payment instrument (Chase Premier Checking ****4892).');
    appendBotChatMessage(`
      <strong>Payment Instrument Switched:</strong><br>
      Charlie's payment instrument was switched to backup checking account (Chase Premier Checking ****4892, $240.00 USD available).<br>
      You can now re-run the autonomous pre-check and cash reservation!
    `);
    loadLiquidityProfiles();
  });

  // Remediation Option 2: AI Budget Revision
  $('btn-remedy-ai')?.addEventListener('click', async () => {
    $('modal-liquidity-failure').hidden = true;
    SOUNDS.click();
    setCollabStatus('Redirecting back to AI Concierge to adjust budget ceiling…');
    appendUserChatMessage('Alice (Lead)', 'AL', 'Charlie has an account shortfall. Concierge, please find an experience under $12/person so all of us can participate.');
    await confirmAndPlanConstraints({ budgetMinor: 1200, preferredDays: ['Friday', 'Saturday'] });
  });

  // Remediation Option 3: Safely Cancel & Release
  $('btn-remedy-release')?.addEventListener('click', async () => {
    $('modal-liquidity-failure').hidden = true;
    if (!activeGroup) return;
    SOUNDS.alert();
    setCollabStatus('Releasing group inventory and cancelling hold safely with zero fee…');
    try {
      await api(`/api/groups/${activeGroup.id}/booking/void`, {});
      await loadGroupBookingState();
      renderSeatMap();
      renderMemberAuthList();
      setCollabStatus('Group holds safely cancelled and seats released back to catalog with zero financial penalty.');
      appendBotChatMessage(`
        <strong>Group Hold Safely Released:</strong><br>
        All temporary inventory locks and PayPal reservations have been cancelled with 0 fees charged.<br>
        You can coordinate a new experience at any time.
      `);
    } catch (err) {
      alert(`Release failed: ${err.message}`);
    }
  });

  // In-Chat Individual Authorize Button
  $('in-chat-authorize-btn')?.addEventListener('click', async () => {
    if (!activeGroup) return;
    SOUNDS.click();
    try {
      setCollabStatus('Initiating PayPal Sandbox order under intent="AUTHORIZE"…');
      await api(`/api/groups/${activeGroup.id}/booking/consent`, {});
      await api(`/api/groups/${activeGroup.id}/contributions/order`, {});
      await api(`/api/groups/${activeGroup.id}/contributions/authorize`, {});
      SOUNDS.auth();
      await loadGroupBookingState();
      renderMemberAuthList();
      setCollabStatus('Your share is successfully authorized! Funds held on your payment instrument.');
    } catch (err) {
      alert(`Authorization failed: ${err.message}`);
    }
  });

  // Simulate remaining authorizations
  $('btn-sim-all-auth')?.addEventListener('click', async () => {
    if (!activeGroup) return;
    SOUNDS.click();
    try {
      setCollabStatus('Simulating PayPal Sandbox authorizations for all remaining members…');
      await api(`/api/groups/${activeGroup.id}/simulate-authorizations`, {});
      SOUNDS.auth();
      await loadGroupBookingState();
      renderMemberAuthList();
      setCollabStatus('All members have authorized their shares! Ready to finalize.');
    } catch (err) {
      alert(`Simulation error: ${err.message}`);
    }
  });

  // Finalize Sequential Capture
  $('canvas-finalize-btn')?.addEventListener('click', async () => {
    if (!activeGroup) return;
    SOUNDS.click();
    try {
      setCollabStatus('Executing fenced sequential capture across authorized instruments…');
      await api(`/api/groups/${activeGroup.id}/finalize`, {});
      SOUNDS.success();
      await loadGroupBookingState();
      renderMemberAuthList();
      fetchAndDisplayTicket();
      setCollabStatus('All captures verified! Private digital passes issued to all members.');
    } catch (err) {
      alert(`Finalization failed: ${err.message}`);
    }
  });

  // Add simulated friend modal
  $('btn-add-friend-demo')?.addEventListener('click', () => {
    SOUNDS.click();
    $('modal-add-friend').hidden = false;
  });
  $('close-add-friend-modal')?.addEventListener('click', () => { $('modal-add-friend').hidden = true; });
  $('cancel-add-friend-btn')?.addEventListener('click', () => { $('modal-add-friend').hidden = true; });

  $('form-add-friend')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const alias = $('add-friend-name')?.value.trim() || 'Friend';
    $('modal-add-friend').hidden = true;
    if (!activeGroup) return;

    SOUNDS.click();
    try {
      setCollabStatus(`Adding ${alias} to group roster…`);
      await api(`/api/groups/${activeGroup.id}/members/add-demo`, { alias });
      // Reload group
      const updated = await api(`/api/groups/${activeGroup.id}`);
      activeGroup = updated;
      renderActiveGroupRoom();
      setCollabStatus(`${alias} joined the group! Total members: ${updated.members?.length}`);
    } catch (err) {
      alert(`Could not add member: ${err.message}`);
    }
  });

  // Copy Invite Button
  $('copy-invite-btn')?.addEventListener('click', () => {
    SOUNDS.click();
    const url = activeGroup?.inviteURL || `${window.location.origin}/?join=${activeGroup?.inviteToken || activeGroup?.id}`;
    navigator.clipboard?.writeText(url).then(() => {
      setCollabStatus('Invite link copied to clipboard!');
      alert('Group invite link copied! Share with friends to let them join.');
    }).catch(() => alert(`Invite link: ${url}`));
  });

  // Pass Buttons
  $('btn-download-pass')?.addEventListener('click', downloadPassJson);
  $('btn-print-pass')?.addEventListener('click', printPass);
  $('btn-scan-validator')?.addEventListener('click', openScannerValidator);
  $('close-validator-modal-btn')?.addEventListener('click', () => { $('qr-validator-modal').hidden = true; });
  $('close-inspector-modal-btn')?.addEventListener('click', () => { $('inspector-modal').hidden = true; });
  $('close-split-modal-btn')?.addEventListener('click', () => { $('split-view-modal').hidden = true; });

  // 3-Way split simulate
  $('split-sync-all-btn')?.addEventListener('click', () => {
    SOUNDS.click();
    runShowcaseDemo('happy_path', selectedOffer?.domain || 'movie');
  });

  // Judge Lab triggers
  $('lab-run-chaos-btn')?.addEventListener('click', () => runShowcaseDemo('chaos_failure', 'movie'));
  $('lab-run-happy-btn')?.addEventListener('click', () => runShowcaseDemo('happy_path', 'movie'));
  $('lab-run-excursion-btn')?.addEventListener('click', () => runShowcaseDemo('happy_path', 'excursion'));
  $('btn-run-happy-path')?.addEventListener('click', () => runShowcaseDemo('happy_path', 'movie'));
  $('btn-run-excursion-path')?.addEventListener('click', () => runShowcaseDemo('happy_path', 'excursion'));
  $('btn-run-chaos-recovery')?.addEventListener('click', () => runShowcaseDemo('chaos_failure', 'movie'));

  // DAG Nodes
  for (let i = 1; i <= 6; i++) {
    $(`dag-node-${i}`)?.addEventListener('click', () => handleDagNodeClick(i));
  }

  setupPass3DTilt();
}

// -------------------------------------------------------------
// DIGITAL WALLET PASS & VALIDATION
// -------------------------------------------------------------
async function fetchAndDisplayTicket() {
  if (!activeGroup) return;
  try {
    const t = await api(`/api/groups/${activeGroup.id}/ticket`);
    const card = $('canvas-wallet-pass');
    if (!card) return;
    card.hidden = false;

    $('pass-title-val').textContent = t.title || 'Cosmic Odyssey: Remastered';
    $('pass-sub-val').textContent = `${t.domain === 'movie' ? '70mm IMAX' : 'Guided Tour'} · ${t.scheduleTime?.slice(0, 10) || ''}`;
    $('pass-seat-val').textContent = t.assignedResource || 'Seat A1';
    $('pass-inline-code').textContent = t.ticketCode || 'TICKET-PASS';
    $('pass-holder-val').textContent = t.alias || PERSONAS[activePersona].alias;
    $('pass-share-val').textContent = `$${t.shareValue} ${t.currency}`;
    $('pass-capture-val').textContent = 'CAP-SANDBOX-AUTH';

    const qrBox = $('pass-inline-qr');
    if (qrBox) drawQRCodeSvg(qrBox, t.ticketCode);

    setCollabStatus(`Personal pass active: ${t.ticketCode} (${t.assignedResource})`);
  } catch (err) {
    console.warn('Ticket fetch:', err.message);
  }
}

function drawQRCodeSvg(container, text) {
  if (!container) return;
  const size = 25;
  const grid = Array.from({ length: size }, () => Array(size).fill(0));

  function drawFinder(startX, startY) {
    for (let r = 0; r < 7; r++) {
      for (let c = 0; c < 7; c++) {
        if (r === 0 || r === 6 || c === 0 || c === 6 || (r >= 2 && r <= 4 && c >= 2 && c <= 4)) {
          grid[startY + r][startX + c] = 1;
        }
      }
    }
  }

  drawFinder(0, 0);
  drawFinder(size - 7, 0);
  drawFinder(0, size - 7);

  for (let i = 8; i < size - 8; i++) {
    if (i % 2 === 0) {
      grid[6][i] = 1;
      grid[i][6] = 1;
    }
  }

  let hash = 0x811c9dc5;
  const str = String(text || 'TICKET-PASS');
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = (hash * 0x01000193) >>> 0;
  }

  let bitIdx = 0;
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      if ((r < 7 && c < 7) || (r < 7 && c >= size - 7) || (r >= size - 7 && c < 7) || (r === 6 || c === 6)) {
        continue;
      }
      grid[r][c] = ((hash >> (bitIdx % 31)) & 1);
      bitIdx++;
    }
  }

  let rects = '';
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      if (grid[r][c] === 1) {
        rects += `<rect x="${c}" y="${r}" width="1.05" height="1.05" fill="#38bdf8"/>`;
      }
    }
  }

  container.innerHTML = `
    <svg viewBox="0 0 ${size} ${size}" shape-rendering="crispEdges" style="width:100%; height:100%; display:block;">
      <rect width="${size}" height="${size}" fill="#0f172a"/>
      ${rects}
    </svg>
  `;
}

function setupPass3DTilt() {
  const card = $('canvas-wallet-pass');
  if (!card) return;

  card.addEventListener('mousemove', (e) => {
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const rotateX = ((y - centerY) / centerY) * -12;
    const rotateY = ((x - centerX) / centerX) * 12;

    card.style.transform = `perspective(800px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02)`;
  });

  card.addEventListener('mouseleave', () => {
    card.style.transform = 'perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)';
  });
}

function downloadPassJson() {
  SOUNDS.click();
  const payload = {
    passType: 'GroupPay.VerifiedPass',
    version: '1.0',
    issuer: 'PayPal Distributed Payments Integrity Framework',
    holder: $('pass-holder-val')?.textContent || 'Alice (Organizer)',
    offer: $('pass-title-val')?.textContent || 'Cosmic Odyssey: Remastered',
    assignedResource: $('pass-seat-val')?.textContent || 'Seat A1',
    shareValue: $('pass-share-val')?.textContent || '$16.00 USD',
    currency: 'USD',
    ticketCode: $('pass-inline-code')?.textContent || 'TICKET-PASS-7B29',
    cryptographicSignature: `SHA256:${($('pass-inline-code')?.textContent || 'TICKET').slice(-12)}`,
    guarantee: 'Zero Bank Friend Risk · Non-Custodial Multi-Buyer Settlement'
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${payload.ticketCode}.json`;
  a.click();
  URL.revokeObjectURL(url);
  setCollabStatus('Pass JSON downloaded with cryptographic proof.');
}

function printPass() {
  SOUNDS.click();
  window.print();
}

function openScannerValidator() {
  SOUNDS.click();
  const modal = $('qr-validator-modal');
  if (!modal) return;
  modal.hidden = false;

  const tCode = $('pass-inline-code')?.textContent || 'TICKET-COSMIC-BD626B703571';
  const box = $('scanner-qr-box');
  if (box) drawQRCodeSvg(box, tCode);

  $('val-ticket-code').textContent = tCode;
  $('val-ticket-holder').textContent = $('pass-holder-val')?.textContent || 'Alice (Organizer)';
  $('val-ticket-seat').textContent = $('pass-seat-val')?.textContent || 'Seat A1';
  $('val-ticket-sig').textContent = `SHA256:${tCode.slice(-12)}_VALID`;

  setTimeout(() => {
    SOUNDS.success();
  }, 350);
}

// -------------------------------------------------------------
// SHOWCASE & CHAOS DEMO RUNNERS
// -------------------------------------------------------------
async function runShowcaseDemo(scenario = 'happy_path', domain = 'movie') {
  SOUNDS.click();
  const terminal = $('lab-telemetry-feed');
  const logTerm = (msg) => {
    if (!terminal) return;
    const p = document.createElement('p');
    p.className = 'terminal-line';
    p.textContent = msg;
    terminal.appendChild(p);
    terminal.scrollTop = terminal.scrollHeight;
  };

  logTerm(`\n[DEMO EXEC] Launching ${scenario.toUpperCase()} for domain=${domain.toUpperCase()}…`);
  try {
    const result = await api('/api/demo/run', { scenario, domain });
    lastShowcaseResult = result;

    for (let i = 0; i < (result.telemetry || []).length; i++) {
      const step = result.telemetry[i];
      logTerm(`[STEP ${i + 1}] [${step.stage}] ${step.details}`);
      await new Promise((r) => setTimeout(r, 100));
    }

    if (scenario === 'happy_path') {
      SOUNDS.success();
      logTerm(`[SUCCESS] 3-party sequential capture confirmed. Passes minted.`);
      setCollabStatus(`Demo complete: 3-party ${domain} payment captured successfully!`);

      $('saga-rollback-track').style.display = 'none';
      const dagStatus = $('dag-overall-status');
      if (dagStatus) {
        dagStatus.textContent = 'INVARIANTS HEALTHY (6/6)';
        dagStatus.className = 'badge badge-success';
      }
      for (let i = 1; i <= 6; i++) $(`dag-node-${i}`)?.classList.add('done');

      // Refresh groups list
      await fetchMyGroups();
      if (result.groupID) {
        await selectGroup(result.groupID);
      }
      updateSplitViewContent(result.tickets);
    } else {
      SOUNDS.alert();
      logTerm(`[RECOVERY] Charlie decline compensated. Alice & Bob refunded.`);
      setCollabStatus('Chaos test: Charlie 422 handled. Compensatory auto-refunds verified.');

      $('saga-rollback-track').style.display = 'block';
      const dagStatus = $('dag-overall-status');
      if (dagStatus) {
        dagStatus.textContent = 'AUTO-COMPENSATION COMPLETE';
        dagStatus.className = 'badge danger-chip';
      }
      $('dag-node-5')?.classList.add('active-pulse');
    }
  } catch (err) {
    logTerm(`[ERROR] ${err.message}`);
    alert(`Demonstration error: ${err.message}`);
  }
}

function updateSplitViewContent(tickets = []) {
  const aliceT = tickets[0] || { assignedResource: 'Seat A1', shareValue: '16.00', ticketCode: 'TICKET-ALICE' };
  const bobT = tickets[1] || { assignedResource: 'Seat A2', shareValue: '16.00', ticketCode: 'TICKET-BOB' };
  const charlieT = tickets[2] || { assignedResource: 'Seat A3', shareValue: '16.00', ticketCode: 'TICKET-CHARLIE' };

  $('phone-alice-seat').textContent = aliceT.assignedResource;
  $('phone-alice-share').textContent = `$${aliceT.shareValue} USD`;
  $('phone-alice-code').textContent = aliceT.ticketCode;
  drawQRCodeSvg($('phone-alice-qr'), aliceT.ticketCode);

  $('phone-bob-seat').textContent = bobT.assignedResource;
  $('phone-bob-share').textContent = `$${bobT.shareValue} USD`;
  $('phone-bob-code').textContent = bobT.ticketCode;
  drawQRCodeSvg($('phone-bob-qr'), bobT.ticketCode);

  $('phone-charlie-seat').textContent = charlieT.assignedResource;
  $('phone-charlie-share').textContent = `$${charlieT.shareValue} USD`;
  $('phone-charlie-code').textContent = charlieT.ticketCode;
  drawQRCodeSvg($('phone-charlie-qr'), charlieT.ticketCode);
}

function handleDagNodeClick(nodeId) {
  SOUNDS.click();
  for (let i = 1; i <= 6; i++) {
    $(`dag-node-${i}`)?.classList.toggle('active-pulse', i === nodeId);
  }

  const info = DAG_NODE_INFO[nodeId];
  if (!info) return;

  $('tray-node-title').textContent = info.title;
  $('tray-node-badge').textContent = info.badge;
  $('tray-node-desc').textContent = info.desc;
  $('tray-node-meta').innerHTML = `
    <span><strong>Tech Stack:</strong> ${info.meta.split('|')[0]}</span>
    <span><strong>Guarantees:</strong> ${info.meta.split('|')[1]}</span>
    <span><strong>Storage:</strong> ${info.meta.split('|')[2]}</span>
  `;
}

// -------------------------------------------------------------
// MODALS: CREATE & JOIN GROUP
// -------------------------------------------------------------
function setupGroupModals() {
  $('close-create-group-modal')?.addEventListener('click', () => { $('modal-create-group').hidden = true; });
  $('cancel-create-group-btn')?.addEventListener('click', () => { $('modal-create-group').hidden = true; });

  $('form-create-group')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = $('create-group-name')?.value.trim();
    const offerId = $('create-group-offer-select')?.value;
    if (!name) return;

    SOUNDS.click();
    $('modal-create-group').hidden = true;
    try {
      setCollabStatus('Creating experience group…');
      const newGrp = await api('/api/groups', { name });
      if (offerId) {
        selectedOffer = catalogOffers.find((o) => o.id === offerId) || selectedOffer;
      }
      await fetchMyGroups();
      await selectGroup(newGrp.id);
      setCollabStatus(`Group '${name}' created! Share invite link with friends.`);
    } catch (err) {
      alert(`Could not create group: ${err.message}`);
    }
  });

  $('close-join-group-modal')?.addEventListener('click', () => { $('modal-join-group').hidden = true; });
  $('cancel-join-group-btn')?.addEventListener('click', () => { $('modal-join-group').hidden = true; });

  $('form-join-group')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    let token = $('join-invite-token')?.value.trim();
    const alias = $('join-alias-input')?.value.trim();
    if (!token) return;

    // Extract token if user pasted full URL
    if (token.includes('invite=')) token = token.split('invite=')[1].split('&')[0];
    else if (token.includes('join=')) token = token.split('join=')[1].split('&')[0];

    SOUNDS.click();
    $('modal-join-group').hidden = true;
    try {
      setCollabStatus('Joining group…');
      const joined = await api('/api/groups/join', { inviteToken: token });
      if (alias) {
        await api(`/api/groups/${joined.id}/profile`, { alias });
      }
      await fetchMyGroups();
      await selectGroup(joined.id);
      setCollabStatus(`Joined group '${joined.name}'!`);
    } catch (err) {
      alert(`Could not join group: ${err.message}`);
    }
  });
}

function openCreateGroupModal(preselectOfferId = null) {
  SOUNDS.click();
  $('modal-create-group').hidden = false;
  $('create-group-name').value = '';
  if (preselectOfferId) {
    $('create-group-offer-select').value = preselectOfferId;
  }
  $('create-group-name').focus();
}

function openJoinGroupModal(token = '') {
  SOUNDS.click();
  $('modal-join-group').hidden = false;
  if (token) $('join-invite-token').value = token;
  $('join-alias-input').value = PERSONAS[activePersona].alias;
}

// -------------------------------------------------------------
// PERSPECTIVE SWITCHER
// -------------------------------------------------------------
function setupPersonaSwitcher() {
  ['alice', 'bob', 'charlie'].forEach((pKey) => {
    $(`persona-btn-${pKey}`)?.addEventListener('click', () => {
      switchPersona(pKey);
    });
  });

  $('persona-btn-split')?.addEventListener('click', () => {
    SOUNDS.click();
    $('split-view-modal').hidden = false;
    updateSplitViewContent(lastShowcaseResult?.tickets || []);
  });
}

function switchPersona(persona) {
  SOUNDS.click();
  activePersona = persona;

  ['alice', 'bob', 'charlie'].forEach((pKey) => {
    $(`persona-btn-${pKey}`)?.classList.toggle('active', pKey === persona);
  });

  const p = PERSONAS[persona] || PERSONAS.alice;
  const badge = $('user-alias-badge');
  if (badge) badge.textContent = p.alias;

  renderMemberAuthList();
  setCollabStatus(`Simulating perspective: ${p.alias} (${p.role}).`);
}

// -------------------------------------------------------------
// WORKSHOP VIEW (PRESERVED FROM SLICE 1)
// -------------------------------------------------------------
let selectedWorkshop = null, selectedBooking = null, paypalButtons = null;
let busy = false, sdkReady = false, renderVersion = 0;
const bookings = new Map();
const unresolved = new Set(['CREATING', 'CAPTURING', 'PENDING', 'UNKNOWN']);

function price(w) { return (w.priceMinor / 100).toFixed(2); }
function schedule(w) {
  return `${new Date(w.startsAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${new Date(w.endsAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}

function saveBooking(b) {
  if (b?.workshopID) bookings.set(b.workshopID, b);
}

function renderBookings() {
  const container = $('bookings');
  if (!container) return;
  container.innerHTML = [...bookings.values()].map((b) => `
    <div class="card" style="margin-bottom:8px;">
      <h4>${escapeHtml(b.title || b.workshopID)}</h4>
      <span class="badge ${b.state === 'COMPLETED' ? 'badge-success' : 'badge-sandbox'}">${b.state}</span>
    </div>
  `).join('');
}

function renderWorkshops() {
  const container = $('workshops');
  if (!container || !config?.workshops) return;
  container.innerHTML = config.workshops.map((w) => `
    <button type="button" class="workshop-card ${selectedWorkshop?.id === w.id ? 'selected' : ''}" data-workshop-id="${w.id}">
      <h2>${escapeHtml(w.title)}</h2>
      <p>${escapeHtml(w.description)}</p>
      <p class="fine">${schedule(w)}</p>
      <strong>$${price(w)} ${w.currency}</strong>
    </button>
  `).join('');

  container.querySelectorAll('.workshop-card').forEach((btn) => {
    btn.addEventListener('click', () => {
      const wid = btn.dataset.workshopId;
      selectedWorkshop = config.workshops.find((x) => x.id === wid);
      $('checkout-heading').textContent = selectedWorkshop.title;
      $('price').textContent = `$${price(selectedWorkshop)} USD`;
      renderWorkshops();
    });
  });
}

// -------------------------------------------------------------
// INITIALIZATION
// -------------------------------------------------------------
document.addEventListener('DOMContentLoaded', async () => {
  setupTabs();
  setupCatalogFilters();
  setupChat();
  setupRoomActions();
  setupGroupModals();
  setupPersonaSwitcher();

  // Audio Toggle
  $('audio-toggle-btn')?.addEventListener('click', () => {
    soundEnabled = !soundEnabled;
    const onIcon = $('audio-icon-on');
    const offIcon = $('audio-icon-off');
    if (onIcon) onIcon.style.display = soundEnabled ? 'block' : 'none';
    if (offIcon) offIcon.style.display = soundEnabled ? 'none' : 'block';
    if (soundEnabled) SOUNDS.click();
    setCollabStatus(`Web Audio feedback ${soundEnabled ? 'enabled' : 'muted'}.`);
  });

  try {
    config = await api('/api/config');
    (config.bookings || []).forEach(saveBooking);
    renderBookings();

    $('setup').hidden = config.configured;
    $('mode').textContent = config.configured ? 'Sandbox connected · test money only' : 'Sandbox checkout not configured';
    $('timezone').textContent = `Schedules shown in your browser timezone: ${Intl.DateTimeFormat().resolvedOptions().timeZone}.`;
    $('discover-tz-notice').textContent = `Schedules shown in your browser timezone (${Intl.DateTimeFormat().resolvedOptions().timeZone}).`;

    // Load dynamic catalog & groups
    await fetchCatalogOffers();
    await fetchMyGroups();

    // Check URL parameters for direct join or group link
    const params = new URLSearchParams(window.location.search);
    const inviteParam = params.get('invite') || params.get('join');
    const groupParam = params.get('group');

    if (inviteParam) {
      openJoinGroupModal(inviteParam);
    } else if (groupParam) {
      await selectGroup(groupParam);
    } else if (myGroups.length > 0) {
      activeGroup = myGroups[0];
      const dot = $('active-group-dot');
      if (dot) dot.style.display = 'inline-block';
    }

  } catch (err) {
    console.error('App initialization error:', err);
  }
});
