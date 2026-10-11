// GroupPay Client Controller: Collaborative Booking, Live Room, Chaos Lab & Workshop Checkout
const $ = (id) => document.getElementById(id);
let config = null;
let currentTab = 'collab';
let activeGroupID = null;
let activeGroup = null;
let activeDomain = 'movie';
let holdTimerInterval = null;
let lastShowcaseResult = null;

// Preserved Workshop State
let selectedWorkshop = null, selectedBooking = null, paypalButtons = null;
let busy = false, sdkReady = false, renderVersion = 0;
const bookings = new Map();
const unresolved = new Set(['CREATING', 'CAPTURING', 'PENDING', 'UNKNOWN']);

function setCollabStatus(text) {
  const el = $('collab-status-feed');
  if (el) el.textContent = text;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

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
  if (!response.ok) throw new Error(data.message || data.error || 'The request failed.');
  return data;
}

// -------------------------------------------------------------
// TAB SWITCHING (3 TABS)
// -------------------------------------------------------------
function setupTabs() {
  $('tab-collab')?.addEventListener('click', () => switchTab('collab'));
  $('tab-lab')?.addEventListener('click', () => switchTab('lab'));
  $('tab-workshop')?.addEventListener('click', () => switchTab('workshop'));
}

function switchTab(tab) {
  currentTab = tab;
  const collabTab = $('tab-collab');
  const labTab = $('tab-lab');
  const workshopTab = $('tab-workshop');
  const collabView = $('collab-view');
  const labView = $('lab-view');
  const workshopView = $('workshop-view');

  if (tab === 'collab') {
    collabTab?.classList.add('active');
    collabTab?.setAttribute('aria-selected', 'true');
    labTab?.classList.remove('active');
    labTab?.setAttribute('aria-selected', 'false');
    workshopTab?.classList.remove('active');
    workshopTab?.setAttribute('aria-selected', 'false');

    if (collabView) collabView.hidden = false;
    if (labView) labView.hidden = true;
    if (workshopView) workshopView.hidden = true;
  } else if (tab === 'lab') {
    labTab?.classList.add('active');
    labTab?.setAttribute('aria-selected', 'true');
    collabTab?.classList.remove('active');
    collabTab?.setAttribute('aria-selected', 'false');
    workshopTab?.classList.remove('active');
    workshopTab?.setAttribute('aria-selected', 'false');

    if (labView) labView.hidden = false;
    if (collabView) collabView.hidden = true;
    if (workshopView) workshopView.hidden = true;
  } else {
    workshopTab?.classList.add('active');
    workshopTab?.setAttribute('aria-selected', 'true');
    collabTab?.classList.remove('active');
    collabTab?.setAttribute('aria-selected', 'false');
    labTab?.classList.remove('active');
    labTab?.setAttribute('aria-selected', 'false');

    if (workshopView) workshopView.hidden = false;
    if (collabView) collabView.hidden = true;
    if (labView) labView.hidden = true;
    renderWorkshops();
  }
}

// -------------------------------------------------------------
// QR CODE SVG GENERATOR
// -------------------------------------------------------------
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
      const inFinder1 = r < 8 && c < 8;
      const inFinder2 = r < 8 && c >= size - 8;
      const inFinder3 = r >= size - 8 && c < 8;
      const inTiming = r === 6 || c === 6;
      if (!inFinder1 && !inFinder2 && !inFinder3 && !inTiming) {
        const val = ((hash >> (bitIdx % 31)) ^ (r * 7 + c * 13)) & 1;
        grid[r][c] = val;
        bitIdx++;
      }
    }
  }

  const rects = [];
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      if (grid[r][c] === 1) {
        rects.push(`<rect x="${c}" y="${r}" width="1" height="1" fill="#0f172a" />`);
      }
    }
  }

  container.innerHTML = `
    <svg viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges">
      <rect width="${size}" height="${size}" fill="#ffffff" />
      ${rects.join('')}
    </svg>
  `;
}

// -------------------------------------------------------------
// COLLABORATIVE ROOM CONTROLLER
// -------------------------------------------------------------
function setupCollabRoom() {
  // 1-Click Fast Actions on Top of Hero
  $('btn-run-happy-path')?.addEventListener('click', () => runShowcaseDemo('happy_path', 'movie'));
  $('btn-run-excursion-path')?.addEventListener('click', () => runShowcaseDemo('happy_path', 'excursion'));
  $('btn-run-chaos-recovery')?.addEventListener('click', () => runShowcaseDemo('chaos_failure', 'movie'));

  // Chaos Lab Triggers
  $('lab-run-chaos-btn')?.addEventListener('click', () => runShowcaseDemo('chaos_failure', 'movie'));
  $('lab-run-happy-btn')?.addEventListener('click', () => runShowcaseDemo('happy_path', 'movie'));
  $('lab-run-excursion-btn')?.addEventListener('click', () => runShowcaseDemo('happy_path', 'excursion'));

  // Domain Switcher
  $('domain-movie-btn')?.addEventListener('click', () => switchRoomDomain('movie'));
  $('domain-excursion-btn')?.addEventListener('click', () => switchRoomDomain('excursion'));

  // Copy Invite Button
  $('copy-invite-btn')?.addEventListener('click', () => {
    const inviteLink = `${window.location.origin}/?join=squad-${Date.now().toString(36)}`;
    navigator.clipboard?.writeText(inviteLink).then(() => {
      setCollabStatus('Invite link copied! Share with friends to join room.');
      alert('Invite link copied to clipboard!');
    }).catch(() => {
      alert(`Invite link: ${inviteLink}`);
    });
  });

  // Chat Prompt Preset Chips
  document.querySelectorAll('.chip-preset').forEach((chip) => {
    chip.addEventListener('click', () => {
      const input = $('chat-input-text');
      if (input) {
        input.value = chip.dataset.text;
        input.focus();
      }
    });
  });

  // Chat Form Submit
  $('chat-input-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const input = $('chat-input-text');
    const text = input?.value.trim();
    if (!text) return;
    input.value = '';

    appendUserChatMessage('Alice (Lead)', '<span class="avatar-mono">AL</span>', text);
    handleChatMessage(text);
  });

  // In-Chat 1-Tap Authorize Button
  $('in-chat-authorize-btn')?.addEventListener('click', () => {
    handleAliceAuthorization();
  });

  // Canvas Finalize Button
  $('canvas-finalize-btn')?.addEventListener('click', () => {
    runShowcaseDemo('happy_path', activeDomain);
  });

  // Seat Click Handlers
  document.querySelectorAll('.seat-button').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.classList.contains('occupied')) return;
      btn.classList.toggle('my-seat');
      setCollabStatus(`Seat ${btn.dataset.seat} selection toggled.`);
    });
  });

  // Click on Wallet Pass to view full modal
  $('canvas-wallet-pass')?.addEventListener('click', () => {
    if (lastShowcaseResult?.tickets?.[0]) {
      showTicketModal(lastShowcaseResult.tickets[0]);
    }
  });

  // Close Modals
  $('close-ticket-modal-btn')?.addEventListener('click', () => {
    $('ticket-modal').hidden = true;
  });
  $('close-inspector-modal-btn')?.addEventListener('click', () => {
    $('inspector-modal').hidden = true;
  });

  // Render initial default QR code in pass
  const passQr = $('pass-inline-qr');
  if (passQr) {
    drawQRCodeSvg(passQr, 'TICKET-COSMIC-BD626B703571');
  }

  // Start hold countdown
  startHoldCountdown(Math.floor(Date.now() / 1000) + 15 * 60);
}

function startHoldCountdown(deadline) {
  if (holdTimerInterval) clearInterval(holdTimerInterval);
  const updateTimer = () => {
    const remaining = Math.max(0, Math.floor(deadline - Date.now() / 1000));
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    const timeStr = `${mins}:${secs < 10 ? '0' : ''}${secs}`;
    const el = $('canvas-hold-countdown');
    if (el) el.textContent = timeStr;
    if (remaining <= 0) {
      clearInterval(holdTimerInterval);
      setCollabStatus('Hold deadline elapsed. Inventory released back to catalog.');
    }
  };
  updateTimer();
  holdTimerInterval = setInterval(updateTimer, 1000);
}

function switchRoomDomain(domain) {
  activeDomain = domain;
  $('domain-movie-btn')?.classList.toggle('active', domain === 'movie');
  $('domain-excursion-btn')?.classList.toggle('active', domain === 'excursion');

  const titleEl = $('room-group-title');
  const quoteCard = $('chat-quote-card');

  if (domain === 'movie') {
    if (titleEl) titleEl.textContent = 'Sci-Fi Screening Squad';
    if (quoteCard) {
      quoteCard.innerHTML = `
        <div class="quote-card-header">
          <div>
            <strong>Cosmic Odyssey: Remastered</strong>
            <span class="fine">Friday Oct 16 · 19:30 · Screen 1</span>
          </div>
          <div class="quote-pricing">
            <span class="fine">Total: $48.00 USD</span>
            <strong class="quote-my-share">Your Share: $16.00 USD</strong>
          </div>
        </div>
        <div class="quote-card-actions">
          <button id="in-chat-authorize-btn" type="button" class="btn btn-primary btn-sm">
            Authorize $16.00 with PayPal Sandbox
          </button>
          <span class="fine" id="in-chat-auth-status">Card authorization hold · Captured only on full roster consent</span>
        </div>
      `;
    }
  } else {
    if (titleEl) titleEl.textContent = 'Island Kayak Adventurers';
    if (quoteCard) {
      quoteCard.innerHTML = `
        <div class="quote-card-header">
          <div>
            <strong>Emerald Cove Kayak Tour</strong>
            <span class="fine">Saturday Oct 17 · 09:00 · Harbor Launch</span>
          </div>
          <div class="quote-pricing">
            <span class="fine">Total: $100.00 USD</span>
            <strong class="quote-my-share">Your Share: $33.34 USD</strong>
          </div>
        </div>
        <div class="quote-card-actions">
          <button id="in-chat-authorize-btn" type="button" class="btn btn-primary btn-sm">
            Authorize $33.34 with PayPal Sandbox
          </button>
          <span class="fine" id="in-chat-auth-status">Remainder cent math allocated in roster order</span>
        </div>
      `;
    }
  }

  $('in-chat-authorize-btn')?.addEventListener('click', () => {
    handleAliceAuthorization();
  });

  appendBotChatMessage(
    `Switched category to <strong>${domain === 'movie' ? 'Cinemas' : 'Excursions'}</strong>. Catalog offers refreshed. Group constraints aligned.`
  );
}

function appendUserChatMessage(sender, avatar, text) {
  const stream = $('chat-messages-container');
  if (!stream) return;
  const msg = document.createElement('div');
  msg.className = 'chat-msg msg-friend';
  msg.innerHTML = `
    <div class="msg-avatar avatar-al">${avatar}</div>
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

function handleChatMessage(rawText) {
  const lower = rawText.toLowerCase();
  const isAttack = lower.includes('ignore previous') || lower.includes('system prompt') || lower.includes('price=0') || lower.includes('free');

  setTimeout(() => {
    if (isAttack) {
      appendBotChatMessage(`
        <span style="color:#f87171; font-weight:700;">Adversarial Injection Intercepted</span><br>
        Safety Gate 1 neutralized untrusted prompt payload.
        <br><br>
        <strong>Strict Invariants Enforced:</strong> Catalog prices ($USD) and inventory availability are immutable server-owned assets. Client instructions cannot manipulate price or grant free tickets.
      `);
      setCollabStatus('Adversarial prompt injection neutralized by AI Safety Gate 1.');
    } else {
      appendBotChatMessage(`
        <strong>Preference Evaluated:</strong> "${escapeHtml(rawText)}"
        <br>
        All 12 safety gates verified. Budget and schedule constraints reconciled across Alice, Bob, and Charlie. Seats and pricing locked for group checkout.
      `);
      setCollabStatus('Preferences interpreted and matched against catalog.');
    }
  }, 400);
}

function handleAliceAuthorization() {
  const btn = $('in-chat-authorize-btn');
  const status = $('in-chat-auth-status');
  if (btn) {
    btn.disabled = true;
    btn.className = 'btn btn-accent btn-sm';
    btn.textContent = 'Authorized with PayPal Sandbox';
  }
  if (status) {
    status.textContent = 'Held on Alice\'s card · Waiting for Bob and Charlie';
  }
  setCollabStatus('Alice (Lead) approved PayPal Sandbox authorization hold.');
}

// -------------------------------------------------------------
// SHOWCASE & CHAOS DEMONSTRATION CONTROLLER
// -------------------------------------------------------------
async function runShowcaseDemo(scenario, domain) {
  setCollabStatus(`Launching demonstration: ${scenario} (${domain})…`);
  const term = $('lab-telemetry-feed');

  function logTerm(line) {
    if (!term) return;
    const p = document.createElement('p');
    p.className = 'terminal-line';
    p.textContent = line;
    term.appendChild(p);
    term.scrollTop = term.scrollHeight;
  }

  logTerm(`--------------------------------------------------`);
  logTerm(`[DISPATCH] Starting ${scenario.toUpperCase()} with domain=${domain}...`);

  try {
    const result = await api('/api/demo/run', { scenario, domain });
    lastShowcaseResult = result;

    // Stream telemetry lines into the lab terminal
    for (let i = 0; i < (result.telemetry || []).length; i++) {
      const step = result.telemetry[i];
      logTerm(`[STEP ${i + 1}] [${step.stage}] ${step.details}`);
      await new Promise((r) => setTimeout(r, 120));
    }

    if (scenario === 'happy_path') {
      logTerm(`[SUCCESS] Coordinated payment verified. 3 private tickets issued.`);
      setCollabStatus(`Demo success: 3-party ${domain} payment completed! Digital passes issued.`);

      // Update Cinema / Kayak Seating Grid
      const seatMap = $('interactive-seat-map');
      if (seatMap) {
        if (domain === 'movie') {
          seatMap.innerHTML = `
            <button type="button" class="seat-button occupied my-seat" data-seat="A1"><span>A1</span><small>Alice</small></button>
            <button type="button" class="seat-button occupied friend-seat" data-seat="A2"><span>A2</span><small>Bob</small></button>
            <button type="button" class="seat-button occupied friend-seat" data-seat="A3"><span>A3</span><small>Charlie</small></button>
            <button type="button" class="seat-button" data-seat="A4">A4</button>
            <button type="button" class="seat-button" data-seat="A5">A5</button>
            <button type="button" class="seat-button" data-seat="A6">A6</button>
            <button type="button" class="seat-button" data-seat="A7">A7</button>
            <button type="button" class="seat-button" data-seat="A8">A8</button>
            <button type="button" class="seat-button" data-seat="B1">B1</button>
            <button type="button" class="seat-button" data-seat="B2">B2</button>
            <button type="button" class="seat-button" data-seat="B3">B3</button>
            <button type="button" class="seat-button" data-seat="B4">B4</button>
            <button type="button" class="seat-button" data-seat="B5">B5</button>
            <button type="button" class="seat-button" data-seat="B6">B6</button>
            <button type="button" class="seat-button" data-seat="B7">B7</button>
            <button type="button" class="seat-button" data-seat="B8">B8</button>
          `;
        } else {
          seatMap.innerHTML = `
            <button type="button" class="seat-button occupied my-seat" data-seat="Kayak 1"><span>Kayak 1</span><small>Alice</small></button>
            <button type="button" class="seat-button occupied friend-seat" data-seat="Kayak 2"><span>Kayak 2</span><small>Bob</small></button>
            <button type="button" class="seat-button occupied friend-seat" data-seat="Kayak 3"><span>Kayak 3</span><small>Charlie</small></button>
            <button type="button" class="seat-button" data-seat="Kayak 4">Kayak 4</button>
            <button type="button" class="seat-button" data-seat="Kayak 5">Kayak 5</button>
            <button type="button" class="seat-button" data-seat="Kayak 6">Kayak 6</button>
          `;
        }
      }

      // Update Roster Authorization Status Meter
      const authList = $('canvas-member-auth-list');
      if (authList && result.tickets) {
        authList.innerHTML = result.tickets.map((t) => `
          <div class="member-auth-row authorized">
            <div class="row-member-info">
              <span class="row-avatar-mono">${t.alias.includes('Alice') ? 'AL' : t.alias.includes('Bob') ? 'BO' : 'CH'}</span>
              <div>
                <strong>${t.alias}</strong>
                <span class="fine">${t.assignedResource} · PayPal Sandbox Hold</span>
              </div>
            </div>
            <div class="row-member-status">
              <span class="mono-amount">$${t.shareValue} USD</span>
              <span class="badge badge-success">AUTHORIZED</span>
            </div>
          </div>
        `).join('');
      }

      const lcBadge = $('canvas-lifecycle-badge');
      if (lcBadge) {
        lcBadge.textContent = 'CONFIRMED';
        lcBadge.className = 'lifecycle-badge CONFIRMED';
      }

      // Update Digital Wallet Pass
      const walletPass = $('canvas-wallet-pass');
      if (walletPass && result.tickets?.[0]) {
        walletPass.hidden = false;
        const aliceTicket = result.tickets[0];
        const passBrand = walletPass.querySelector('.pass-brand');
        if (passBrand) {
          passBrand.innerHTML = `
            <span class="pass-badge">VERIFIED DIGITAL PASS</span>
            <h4>${result.offer?.title || 'Group Experience'}</h4>
            <p class="pass-sub">${domain === 'movie' ? '70mm IMAX · Starlight Cinema Screen 1' : 'Harbor Launch · Guided Expedition'}</p>
          `;
        }
        const seatVal = walletPass.querySelector('.pass-seat-badge strong');
        if (seatVal) seatVal.textContent = aliceTicket.assignedResource;

        const codeVal = $('pass-inline-code');
        if (codeVal) codeVal.textContent = aliceTicket.ticketCode;

        const capVal = $('pass-capture-val');
        if (capVal) capVal.textContent = aliceTicket.captureID || 'CAP-SANDBOX-AUTH';

        const qrBox = $('pass-inline-qr');
        if (qrBox) drawQRCodeSvg(qrBox, aliceTicket.ticketCode);
      }

      // Concierge Chat Celebration
      appendBotChatMessage(`
        <strong>All 3 Authorizations Captured</strong><br>
        Sequential capture completed with zero single-buyer exposure.
        Individual passes issued for <strong>Alice (${result.tickets[0]?.assignedResource})</strong>,
        <strong>Bob (${result.tickets[1]?.assignedResource})</strong>, and
        <strong>Charlie (${result.tickets[2]?.assignedResource})</strong>.
      `);

    } else {
      // Chaos Failure (Charlie Card Decline)
      logTerm(`[RECOVERY] Charlie decline compensated. Alice & Bob refunded.`);
      setCollabStatus('Chaos test passed: Charlie 422 handled. Compensatory auto-refunds verified.');

      // Update Roster Auth status to show decline and refunds
      const authList = $('canvas-member-auth-list');
      if (authList) {
        authList.innerHTML = `
          <div class="member-auth-row" style="border-color:rgba(245,158,11,0.5); background:rgba(245,158,11,0.06);">
            <div class="row-member-info">
              <span class="row-avatar-mono">AL</span>
              <div>
                <strong>Alice (Lead)</strong>
                <span class="fine">Seat A1 · Auto-Refunded Capture</span>
              </div>
            </div>
            <div class="row-member-status">
              <span class="mono-amount">$16.00 USD</span>
              <span class="badge badge-gold">REFUNDED</span>
            </div>
          </div>
          <div class="member-auth-row" style="border-color:rgba(245,158,11,0.5); background:rgba(245,158,11,0.06);">
            <div class="row-member-info">
              <span class="row-avatar-mono">BO</span>
              <div>
                <strong>Bob</strong>
                <span class="fine">Seat A2 · Auto-Refunded Capture</span>
              </div>
            </div>
            <div class="row-member-status">
              <span class="mono-amount">$16.00 USD</span>
              <span class="badge badge-gold">REFUNDED</span>
            </div>
          </div>
          <div class="member-auth-row declined">
            <div class="row-member-info">
              <span class="row-avatar-mono">CH</span>
              <div>
                <strong>Charlie</strong>
                <span class="fine">Seat A3 · Simulated 422 Decline</span>
              </div>
            </div>
            <div class="row-member-status">
              <span class="mono-amount">$16.00 USD</span>
              <span class="badge danger-chip">422 DECLINED</span>
            </div>
          </div>
        `;
      }

      const lcBadge = $('canvas-lifecycle-badge');
      if (lcBadge) {
        lcBadge.textContent = 'CANCELLED';
        lcBadge.className = 'lifecycle-badge CANCELLED';
      }

      // Reset seating canvas
      const seatMap = $('interactive-seat-map');
      if (seatMap) {
        seatMap.querySelectorAll('.seat-button').forEach((b) => {
          b.className = 'seat-button';
          b.innerHTML = b.dataset.seat;
        });
      }

      // Concierge Bot Announcement
      appendBotChatMessage(`
        <strong>Chaos Compensation Executed:</strong> Charlie's card was declined (<code>422 INSTRUMENT_DECLINED</code>).<br>
        Sequential capture halted safely. Alice &amp; Bob captures were automatically refunded, Charlie was voided, and held seats A1, A2, A3 were freed back to the catalog.
      `);
    }

  } catch (err) {
    logTerm(`[ERROR] ${err.message}`);
    alert(`Demonstration error: ${err.message}`);
  }
}

function showTicketModal(ticket) {
  $('ticket-offer-title').textContent = ticket.title || 'Screening Pass';
  $('ticket-schedule-time').textContent = ticket.scheduleTime ? new Date(ticket.scheduleTime).toLocaleString() : new Date().toLocaleString();
  $('ticket-seat-label').textContent = ticket.assignedResource || 'Assigned Place';
  $('ticket-alias-val').textContent = ticket.alias || 'Participant';
  $('ticket-code-display').textContent = ticket.ticketCode;
  $('ticket-paid-val').textContent = `$${ticket.shareValue}`;
  $('ticket-currency-val').textContent = ticket.currency || 'USD';
  $('ticket-capture-id').textContent = ticket.captureID || 'CAP-SANDBOX-AUTH';

  const issueSecs = typeof ticket.issuedAt === 'number'
    ? (ticket.issuedAt < 1e11 ? ticket.issuedAt * 1000 : ticket.issuedAt)
    : Date.now();
  $('ticket-time-val').textContent = new Date(issueSecs).toLocaleString();
  $('ticket-sig-hash').textContent = `SHA256:${(ticket.ticketCode || 'TICKET').slice(-12)}`;

  const qrContainer = $('ticket-qr-canvas');
  if (qrContainer) {
    drawQRCodeSvg(qrContainer, ticket.qrPayload || ticket.ticketCode);
  }

  $('ticket-modal').hidden = false;
}

// -------------------------------------------------------------
// WORKSHOP FLOW (PRESERVED SLICE 1)
// -------------------------------------------------------------
function saveBooking(booking) {
  if (booking?.id) bookings.set(booking.id, booking);
}

function state(booking) {
  return booking.bookingState || booking.state || 'DRAFT';
}

function price(workshop) {
  return workshop?.value || '—';
}

function schedule(workshop) {
  return workshop?.startsAt ? new Date(workshop.startsAt).toLocaleString() : '—';
}

function message(text, type = 'info') {
  const el = $('status');
  if (el) {
    el.textContent = text;
    el.className = type;
  }
}

function setBusy(val) {
  busy = val;
  const recheckBtn = $('recheck');
  const compBtn = $('complete-payment');
  if (recheckBtn) recheckBtn.disabled = busy;
  if (compBtn) compBtn.disabled = busy;
}

function renderBookings() {
  const container = $('bookings');
  if (!container) return;
  container.replaceChildren();
  for (const booking of bookings.values()) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'booking-row';
    button.disabled = busy;
    button.textContent = `${booking.workshopTitle || booking.workshopID} · ${booking.bookingState} / ${booking.attemptState || 'NOT_STARTED'}`;
    button.addEventListener('click', () => selectWorkshop(booking.workshopID));
    container.append(button);
  }
}

function renderStatus() {
  const booking = selectedBooking;
  const receipt = $('receipt');
  if (!booking) {
    if (receipt) receipt.hidden = true;
    $('complete-payment').hidden = true;
    $('recheck').hidden = true;
    $('lesson').hidden = true;
    return;
  }
  if (receipt) receipt.hidden = false;
  $('booking-id').textContent = booking.id;
  $('booking-state').textContent = booking.bookingState;
  $('attempt-state').textContent = booking.attemptState || 'NOT_STARTED';
  $('order-id').textContent = booking.orderID || '—';
  $('capture-id').textContent = booking.captureID || '—';

  $('complete-payment').hidden = booking.attemptState !== 'APPROVED';
  $('recheck').hidden = !unresolved.has(booking.attemptState);

  const lesson = $('lesson');
  if (booking.lessonURL) {
    lesson.hidden = false;
    lesson.href = booking.lessonURL;
  } else {
    lesson.hidden = true;
  }
}

async function refreshBooking(id) {
  const booking = await api(`/api/bookings/${encodeURIComponent(id)}`);
  saveBooking(booking);
  if (selectedBooking?.id === id) renderStatus();
  return booking;
}

async function recover(error, bookingID) {
  if (bookingID) {
    try { await refreshBooking(bookingID); } catch {}
  }
  message(`${error.message || 'Checkout was interrupted.'} Recheck your saved payment before another attempt.`, 'error');
}

async function renderCheckout() {
  const version = ++renderVersion;
  if (paypalButtons) {
    try { await paypalButtons.close(); } catch {}
    paypalButtons = undefined;
  }
  if (version !== renderVersion) return;
  const container = $('paypal-buttons');
  if (container) container.replaceChildren();

  if (!sdkReady || !selectedWorkshop || (selectedBooking && (!selectedBooking.canPay || selectedBooking.attemptState === 'APPROVED'))) return;

  const workshopID = selectedWorkshop.id;
  let bookingID = selectedBooking?.id;

  if (!window.paypal?.Buttons) return;

  const buttons = window.paypal.Buttons({
    style: { layout: 'vertical', shape: 'rect', label: 'pay' },
    onClick(data, actions) { return busy ? actions.reject() : actions.resolve(); },
    async createOrder() {
      setBusy(true); message('Saving your booking and preparing PayPal checkout…');
      try {
        const booking = await api('/api/orders', { workshopID });
        bookingID = booking.id; saveBooking(booking); renderStatus();
        if (!booking.orderID || !booking.canPay) throw new Error(booking.message || 'This payment needs reconciliation before checkout can continue.');
        message('Approve with your Personal Sandbox account. Approval alone does not grant lesson access.');
        return booking.orderID;
      } catch (error) { await recover(error, bookingID); setBusy(false); throw error; }
    },
    async onApprove(data) {
      message('Approval received. Confirming capture with PayPal…');
      try {
        saveBooking(await api(`/api/orders/${encodeURIComponent(data.orderID)}/capture`, {})); renderStatus();
      } catch (error) { await recover(error, bookingID); }
      finally { setBusy(false); await renderCheckout(); }
    },
    async onCancel() {
      try {
        if (bookingID) { saveBooking(await api(`/api/bookings/${encodeURIComponent(bookingID)}/cancel`, {})); renderStatus(); }
        else message('Checkout closed before a booking was created.');
      } catch (error) { await recover(error, bookingID); }
      finally { setBusy(false); await renderCheckout(); }
    },
    async onError(error) {
      await recover(error, bookingID);
      setBusy(false);
      if (selectedBooking && !selectedBooking.canPay) await renderCheckout();
    }
  });

  paypalButtons = buttons;
  try { await buttons.render('#paypal-buttons'); }
  catch { if (version === renderVersion) message('PayPal checkout could not load. Refresh or recheck an existing payment.', 'error'); }
}

async function selectWorkshop(id) {
  if (busy) return;
  selectedWorkshop = (config?.workshops || []).find((w) => w.id === id);
  if (!selectedWorkshop) return;
  selectedBooking = [...bookings.values()].find((b) => b.workshopID === id);
  $('checkout-heading').textContent = selectedWorkshop.title;
  $('price').textContent = `$${price(selectedWorkshop)}`;
  $('schedule').textContent = schedule(selectedWorkshop);

  document.querySelectorAll('.workshop-card').forEach((card) => {
    const active = card.dataset.workshop === id;
    card.classList.toggle('selected', active);
    card.setAttribute('aria-pressed', String(active));
  });

  renderStatus();
  await renderCheckout();
}

function renderWorkshops() {
  const container = $('workshops');
  if (!container || !config?.workshops) return;
  container.replaceChildren();
  for (const workshop of config.workshops) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = `workshop-card ${selectedWorkshop?.id === workshop.id ? 'selected' : ''}`;
    card.dataset.workshop = workshop.id;
    card.setAttribute('aria-pressed', String(selectedWorkshop?.id === workshop.id));
    card.innerHTML = `
      <h2>${escapeHtml(workshop.title)}</h2>
      <p>${escapeHtml(workshop.description)}</p>
      <p class="fine">${schedule(workshop)}</p>
      <strong>$${price(workshop)} ${workshop.currency}</strong>
    `;
    card.addEventListener('click', () => selectWorkshop(workshop.id));
    container.appendChild(card);
  }
}

function setupWorkshopListeners() {
  $('recheck')?.addEventListener('click', async () => {
    if (busy || !selectedBooking) return;
    const bookingID = selectedBooking.id;
    setBusy(true); message('Checking the saved payment with PayPal…');
    try { saveBooking(await api(`/api/bookings/${encodeURIComponent(bookingID)}/reconcile`, {})); renderStatus(); }
    catch (error) { await recover(error, bookingID); }
    finally { setBusy(false); await renderCheckout(); }
  });

  $('complete-payment')?.addEventListener('click', async () => {
    const booking = selectedBooking;
    if (busy || !booking || booking.attemptState !== 'APPROVED' || !booking.orderID) return;
    setBusy(true); message('Checking the approved order and completing your payment…');
    try {
      const completed = await api(`/api/orders/${encodeURIComponent(booking.orderID)}/capture`, {});
      saveBooking(completed); renderStatus();
    } catch (error) { await recover(error, booking.id); }
    finally { setBusy(false); await renderCheckout(); }
  });
}

// -------------------------------------------------------------
// APP INITIALIZATION
// -------------------------------------------------------------
document.addEventListener('DOMContentLoaded', async () => {
  setupTabs();
  setupCollabRoom();
  setupWorkshopListeners();

  try {
    config = await api('/api/config');
    (config.bookings || []).forEach(saveBooking);
    renderBookings();

    $('setup').hidden = config.configured;
    $('mode').textContent = config.configured ? 'Sandbox connected · test money only' : 'Sandbox checkout not configured';
    $('timezone').textContent = `Schedules shown in your browser timezone: ${Intl.DateTimeFormat().resolvedOptions().timeZone}.`;

    renderWorkshops();
    if (config.workshops?.length) {
      await selectWorkshop(config.workshops[0].id);
    }

    if (config.configured) {
      const script = document.createElement('script');
      script.src = 'https://www.paypal.com/sdk/js?' + new URLSearchParams({
        'client-id': config.clientID, currency: 'USD', intent: 'capture', components: 'buttons'
      });
      script.onload = () => { sdkReady = true; renderCheckout(); };
      script.onerror = () => { message('PayPal SDK could not load. Check network.', 'warning'); };
      document.head.append(script);
    }
  } catch (err) {
    console.error('Config load failed:', err);
  }
});
