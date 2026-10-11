// GroupPay Client Controller: Collaborative Booking & Workshop Checkout
const $ = (id) => document.getElementById(id);
let config = null;
let currentTab = 'collab';
let activeGroupID = null;
let activeGroup = null;
let activeBookingView = null;
let activeDomain = 'movie';
let selectedOfferID = null;
let selectedResourceIDs = [];
let holdTimerInterval = null;

// Preserved Workshop State
let selectedWorkshop = null, selectedBooking = null, paypalButtons = null;
let busy = false, sdkReady = false, renderVersion = 0;
const bookings = new Map();
const unresolved = new Set(['CREATING', 'CAPTURING', 'PENDING', 'UNKNOWN']);

function setCollabStatus(text) {
  const el = $('collab-status-feed');
  if (el) el.textContent = text;
}

async function api(path, body) {
  const options = { credentials: 'same-origin', cache: 'no-store' };
  if (body !== undefined) {
    options.method = 'POST';
    options.headers = { 'Content-Type': 'application/json', 'X-CSRF-Token': config.csrfToken };
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
// TAB SWITCHING
// -------------------------------------------------------------
function setupTabs() {
  $('tab-collab').addEventListener('click', () => switchTab('collab'));
  $('tab-workshop').addEventListener('click', () => switchTab('workshop'));
}

function switchTab(tab) {
  currentTab = tab;
  if (tab === 'collab') {
    $('tab-collab').classList.add('active');
    $('tab-workshop').classList.remove('active');
    $('collab-view').hidden = false;
    $('workshop-view').hidden = true;
  } else {
    $('tab-workshop').classList.add('active');
    $('tab-collab').classList.remove('active');
    $('workshop-view').hidden = false;
    $('collab-view').hidden = true;
    renderWorkshops();
  }
}

// -------------------------------------------------------------
// COLLABORATIVE BOOKING FLOW
// -------------------------------------------------------------
function setupCollabFlow() {
  // Step 1: Create Group
  $('collab-create-group-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = $('collab-group-name').value.trim();
    if (!name) return;
    try {
      setCollabStatus('Creating collaborative group…');
      const created = await api('/api/groups', { name });
      activeGroupID = created.id;
      setCollabStatus(`Group "${created.name}" created! Share the invite link with your friends.`);
      await loadGroupDetails(activeGroupID);
    } catch (err) {
      alert(err.message);
    }
  });

  // Join Group
  $('collab-join-group-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const token = $('collab-invite-token').value.trim();
    if (!token) return;
    try {
      setCollabStatus('Joining group…');
      const joined = await api('/api/groups/join', { inviteToken: token });
      activeGroupID = joined.id;
      setCollabStatus(`Joined group "${joined.name}"!`);
      await loadGroupDetails(activeGroupID);
    } catch (err) {
      alert(err.message);
    }
  });

  // Copy Invite
  $('copy-invite-btn').addEventListener('click', () => {
    if (!activeGroup?.inviteURL) return;
    navigator.clipboard.writeText(activeGroup.inviteURL).then(() => {
      alert('Invite link copied to clipboard! Send to friends to join.');
    });
  });

  // Set Profile Alias
  $('set-profile-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const alias = $('profile-alias').value.trim();
    if (!alias || !activeGroupID) return;
    try {
      await api(`/api/groups/${activeGroupID}/profile`, { alias });
      $('user-alias-badge').textContent = alias;
      setCollabStatus(`Display alias set to "${alias}".`);
      await loadGroupDetails(activeGroupID);
    } catch (err) {
      alert(err.message);
    }
  });

  // Domain Switcher
  $('domain-movie-btn').addEventListener('click', () => switchDomain('movie'));
  $('domain-excursion-btn').addEventListener('click', () => switchDomain('excursion'));

  // Preset Chips
  document.querySelectorAll('.chip-preset').forEach((chip) => {
    chip.addEventListener('click', () => {
      $('pref-input').value = chip.dataset.text;
    });
  });

  // Step 2: Preference Submit
  $('preference-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = $('pref-input').value.trim();
    if (!text || !activeGroupID) {
      alert('Please create or join a group first.');
      return;
    }
    try {
      setCollabStatus('Analyzing preferences with AI…');
      const res = await api(`/api/groups/${activeGroupID}/preferences`, {
        rawText: text,
        userTz: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
      });
      renderAIInterpretation(res.interpretation);
      $('confirm-pref-btn').hidden = false;
      setCollabStatus('Preferences interpreted! Review and confirm your constraints.');
      await refreshGroupPlan();
    } catch (err) {
      alert(err.message);
    }
  });

  // Confirm Preference
  $('confirm-pref-btn').addEventListener('click', async () => {
    if (!activeGroupID || !window._lastInterpreted) return;
    try {
      setCollabStatus('Confirming hard constraints…');
      await api(`/api/groups/${activeGroupID}/preferences/confirm`, {
        confirmedConstraints: window._lastInterpreted
      });
      $('ai-status-indicator').textContent = 'CONFIRMED';
      $('ai-status-indicator').classList.add('confirmed');
      $('confirm-pref-btn').hidden = true;
      setCollabStatus('Constraints confirmed! Group plan updated.');
      await refreshGroupPlan();
    } catch (err) {
      alert(err.message);
    }
  });

  // View Ticket Button
  $('view-ticket-btn').addEventListener('click', async () => {
    if (!activeGroupID) return;
    try {
      const ticket = await api(`/api/groups/${activeGroupID}/ticket`);
      showTicketModal(ticket);
    } catch (err) {
      alert(err.message);
    }
  });

  // Close Ticket Modal
  $('close-ticket-modal-btn').addEventListener('click', () => {
    $('ticket-modal').hidden = true;
  });
}

function switchDomain(domain) {
  activeDomain = domain;
  $('domain-movie-btn').classList.toggle('active', domain === 'movie');
  $('domain-excursion-btn').classList.toggle('active', domain === 'excursion');
  refreshGroupPlan();
}

async function loadGroupDetails(groupID) {
  try {
    const group = await api(`/api/groups/${groupID}`);
    activeGroup = group;
    $('no-group-panel').hidden = true;
    $('active-group-panel').hidden = false;
    $('active-group-name').textContent = group.name;
    $('active-group-role').textContent = group.isOrganizer ? 'Organizer' : 'Member';

    // Roster Chips
    const chipsContainer = $('roster-chips');
    chipsContainer.replaceChildren();
    for (const m of group.members || []) {
      const chip = document.createElement('span');
      chip.className = `member-chip ${m.isOrganizer ? 'organizer' : ''}`;
      chip.textContent = `${m.alias || 'Member'} ${m.isOrganizer ? '👑' : ''}`;
      chipsContainer.appendChild(chip);
    }

    await refreshGroupPlan();
    await refreshBookingView();
  } catch (err) {
    setCollabStatus(`Error loading group: ${err.message}`);
  }
}

function renderAIInterpretation(interp) {
  window._lastInterpreted = interp;
  const card = $('ai-interpretation-card');
  card.hidden = false;
  $('ai-status-indicator').textContent = interp.injection_detected ? 'SECURITY NEUTRALIZED' : 'UNCONFIRMED';
  $('ai-status-indicator').className = interp.injection_detected ? 'ai-status-badge danger-chip' : 'ai-status-badge';

  const grid = $('ai-structured-details');
  grid.replaceChildren();

  const items = [
    { label: 'Max Budget', val: interp.budget_cents ? `$${(interp.budget_cents / 100).toFixed(2)}` : 'Standard' },
    { label: 'Preferred Days', val: interp.preferred_days?.length ? interp.preferred_days.join(', ') : 'Any' },
    { label: 'Time Window', val: interp.time_window?.earliest || interp.time_window?.latest || interp.time_window?.finish_before ? `${interp.time_window.earliest || '00:00'} - ${interp.time_window.latest || interp.time_window.finish_before || '23:59'}` : 'Flexible' }
  ];

  for (const item of items) {
    const d = document.createElement('div');
    d.className = 'ai-item';
    d.innerHTML = `<span class="ai-item-label">${item.label}</span><strong>${item.val}</strong>`;
    grid.appendChild(d);
  }

  const clar = $('ai-clarifications');
  clar.replaceChildren();
  if (interp.clarifications?.length) {
    for (const c of interp.clarifications) {
      const p = document.createElement('p');
      p.textContent = `ℹ️ ${c}`;
      clar.appendChild(p);
    }
  }
}

async function refreshGroupPlan() {
  if (!activeGroupID) return;
  try {
    const plan = await api(`/api/groups/${activeGroupID}/plan?domain=${activeDomain}`);
    $('group-plan-card').hidden = false;
    $('plan-confirmation-status').textContent = plan.allConfirmed
      ? '✓ All members confirmed'
      : `${plan.confirmedCount}/${plan.memberCount} members confirmed`;

    $('plan-explanation-text').textContent = plan.explanation;

    // Render Matches
    const matchesGrid = $('plan-matches-list');
    matchesGrid.replaceChildren();
    for (const offer of plan.matches || []) {
      const card = document.createElement('div');
      card.className = `offer-plan-card ${selectedOfferID === offer.id ? 'selected' : ''}`;
      card.innerHTML = `
        <div class="offer-plan-info">
          <h4>${offer.title}</h4>
          <p>${new Date(offer.scheduleTime).toLocaleString()} · ${offer.domain.toUpperCase()}</p>
        </div>
        <div class="offer-plan-pricing">
          <strong>$${offer.value}</strong>
          <span>${offer.domain === 'movie' ? 'per ticket' : 'fixed group'}</span>
        </div>
      `;
      card.addEventListener('click', () => selectOffer(offer));
      matchesGrid.appendChild(card);
    }

    // Render Conflicts if any
    const conflictsList = $('plan-conflicts-list');
    if (plan.conflicts?.length) {
      conflictsList.hidden = false;
      conflictsList.replaceChildren();
      for (const c of plan.conflicts) {
        const p = document.createElement('p');
        p.textContent = `⚠️ [${c.type}] ${c.reason}`;
        conflictsList.appendChild(p);
      }
    } else {
      conflictsList.hidden = true;
    }
  } catch (err) {
    console.error('Error fetching plan:', err);
  }
}

async function selectOffer(offer) {
  selectedOfferID = offer.id;
  selectedResourceIDs = [];
  document.querySelectorAll('.offer-plan-card').forEach((c) => c.classList.remove('selected'));
  renderSeatingAndQuote(offer);
}

async function renderSeatingAndQuote(offer) {
  const container = $('quote-container');
  container.replaceChildren();

  // Quote details
  const quote = await api(`/api/groups/${activeGroupID}/quote`, { offerID: offer.id });
  const memberCount = activeGroup?.members?.length || 2;

  const quoteBox = document.createElement('div');
  quoteBox.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <div>
        <h4 style="font-size:16px;">${quote.title}</h4>
        <p class="fine">${quote.roundingRule}</p>
      </div>
      <div style="text-align:right;">
        <span style="font-size:12px; color:var(--text-dim);">Authoritative Total:</span>
        <strong style="font-size:22px; color:var(--accent); display:block;">$${quote.totalValue} ${quote.currency}</strong>
      </div>
    </div>
  `;

  // Seat Selector
  const seatTitle = document.createElement('p');
  seatTitle.className = 'seating-title';
  seatTitle.textContent = `Select ${memberCount} adjacent ${offer.domain === 'movie' ? 'seats' : 'places'}:`;
  quoteBox.appendChild(seatTitle);

  const seatGrid = document.createElement('div');
  seatGrid.className = 'seat-map-grid';

  for (const res of offer.resources || []) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `seat-button ${res.state.toLowerCase()}`;
    btn.textContent = res.label;
    btn.disabled = res.state !== 'FREE';

    btn.addEventListener('click', () => {
      if (selectedResourceIDs.includes(res.id)) {
        selectedResourceIDs = selectedResourceIDs.filter((id) => id !== res.id);
        btn.classList.remove('selected');
      } else if (selectedResourceIDs.length < memberCount) {
        selectedResourceIDs.push(res.id);
        btn.classList.add('selected');
      }
      updateFreezeButtonState(freezeBtn, memberCount);
    });
    seatGrid.appendChild(btn);
  }
  quoteBox.appendChild(seatGrid);

  // Shares table
  const table = document.createElement('table');
  table.className = 'quote-table';
  table.innerHTML = `
    <thead>
      <tr><th>Member Alias</th><th>Assigned Seat/Place</th><th>Exact Share Amount</th></tr>
    </thead>
    <tbody>
      ${quote.shares.map((s, idx) => `
        <tr>
          <td>${activeGroup.members[idx]?.alias || `Member ${idx + 1}`}</td>
          <td id="table-res-${idx}">${selectedResourceIDs[idx] ? 'Selected' : 'Pending selection'}</td>
          <td><strong>$${s.shareValue} USD</strong></td>
        </tr>
      `).join('')}
    </tbody>
  `;
  quoteBox.appendChild(table);

  // Freeze Button
  const freezeBtn = document.createElement('button');
  freezeBtn.type = 'button';
  freezeBtn.className = 'btn btn-primary';
  freezeBtn.textContent = '🔒 Freeze Roster & Hold Inventory (15m)';
  freezeBtn.disabled = selectedResourceIDs.length !== memberCount || !activeGroup.isOrganizer;

  freezeBtn.addEventListener('click', async () => {
    try {
      setCollabStatus('Freezing roster and holding inventory…');
      await api(`/api/groups/${activeGroupID}/freeze`, {
        offerID: offer.id,
        resourceIDs: selectedResourceIDs
      });
      setCollabStatus('Roster frozen! 15-minute hold active. Participants can now approve individual holds.');
      await refreshBookingView();
    } catch (err) {
      alert(err.message);
    }
  });

  quoteBox.appendChild(freezeBtn);
  container.appendChild(quoteBox);
}

function updateFreezeButtonState(btn, needed) {
  if (btn) btn.disabled = selectedResourceIDs.length !== needed || !activeGroup?.isOrganizer;
}

async function refreshBookingView() {
  if (!activeGroupID) return;
  try {
    const booking = await api(`/api/groups/${activeGroupID}/booking`);
    activeBookingView = booking;

    if (!booking.hasBooking) {
      $('booking-lifecycle-pill').textContent = 'DRAFT';
      $('booking-lifecycle-pill').className = 'lifecycle-badge';
      $('hold-timer-bar').hidden = true;
      $('monitor-my-share').textContent = '—';
      $('monitor-total').textContent = '—';
      $('monitor-ticket-card').hidden = true;
      return;
    }

    $('booking-lifecycle-pill').textContent = booking.state;
    $('booking-lifecycle-pill').className = `lifecycle-badge ${booking.state}`;
    $('monitor-total').textContent = `$${booking.totalValue} ${booking.currency}`;

    // My Share
    if (booking.myShare) {
      $('monitor-my-share').textContent = `$${booking.myShare.shareValue}`;
    }

    // Hold Timer
    if (booking.holdDeadline && booking.state === 'AWAITING_AUTHORIZATIONS') {
      $('hold-timer-bar').hidden = false;
      startHoldCountdown(booking.holdDeadline);
    } else {
      $('hold-timer-bar').hidden = true;
      if (holdTimerInterval) clearInterval(holdTimerInterval);
    }

    // Roster Progress in Monitor
    const progList = $('monitor-roster-progress');
    progList.replaceChildren();
    for (const p of booking.rosterProgress || []) {
      const row = document.createElement('div');
      row.className = 'progress-row';
      const statusClass = p.hasAuthorized ? 'authorized' : p.hasConsented ? 'consented' : 'pending';
      const statusText = p.hasAuthorized ? 'Authorized' : p.hasConsented ? 'Consented' : 'Pending';
      row.innerHTML = `
        <strong>${p.alias}</strong>
        <span class="progress-status-badge ${statusClass}">${statusText}</span>
      `;
      progList.appendChild(row);
    }

    // Step 4: Authorization Panel
    renderAuthorizationPanel(booking);

    // Step 5: Finalization Panel
    renderFinalizationPanel(booking);

    // Check confirmed ticket
    if (booking.state === 'CONFIRMED') {
      try {
        const ticket = await api(`/api/groups/${activeGroupID}/ticket`);
        $('monitor-ticket-card').hidden = false;
        $('monitor-ticket-code').textContent = ticket.ticketCode;
        $('monitor-ticket-seat').textContent = `${ticket.title} · ${ticket.assignedResource}`;
      } catch {
        $('monitor-ticket-card').hidden = true;
      }
    } else {
      $('monitor-ticket-card').hidden = true;
    }
  } catch (err) {
    console.error('Error refreshing booking view:', err);
  }
}

function startHoldCountdown(deadline) {
  if (holdTimerInterval) clearInterval(holdTimerInterval);
  const updateTimer = () => {
    const remaining = Math.max(0, Math.floor(deadline - Date.now() / 1000));
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    $('hold-countdown').textContent = `${mins}:${secs < 10 ? '0' : ''}${secs}`;
    if (remaining <= 0) {
      clearInterval(holdTimerInterval);
      setCollabStatus('Hold deadline has elapsed. Please void and re-reserve.');
    }
  };
  updateTimer();
  holdTimerInterval = setInterval(updateTimer, 1000);
}

function renderAuthorizationPanel(booking) {
  const panel = $('authorization-panel');
  panel.replaceChildren();

  const share = booking.myShare;
  if (!share) {
    panel.innerHTML = '<p class="fine">You are not assigned a share in this booking.</p>';
    return;
  }

  const box = document.createElement('div');
  box.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <div>
        <strong>Your Share: $${share.shareValue} USD</strong>
        <p class="fine">Assigned: ${share.assignedResource || 'Resource'}</p>
      </div>
      <span class="role-badge">${share.state}</span>
    </div>
  `;

  // Consent Button
  if (!share.consentGiven) {
    const consentBtn = document.createElement('button');
    consentBtn.type = 'button';
    consentBtn.className = 'btn btn-secondary';
    consentBtn.textContent = 'Give Participant Consent';
    consentBtn.addEventListener('click', async () => {
      try {
        await api(`/api/groups/${activeGroupID}/booking/consent`, {});
        setCollabStatus('Consent recorded! You can now authorize your payment.');
        await refreshBookingView();
      } catch (err) {
        alert(err.message);
      }
    });
    box.appendChild(consentBtn);
  } else if (share.state === 'PENDING_CONSENT' || share.state === 'ACCEPTED' || share.state === 'AWAITING_APPROVAL') {
    // Authorize Button
    const authBtn = document.createElement('button');
    authBtn.type = 'button';
    authBtn.className = 'btn btn-primary';
    authBtn.textContent = `Authorize $${share.shareValue} with PayPal Sandbox`;

    authBtn.addEventListener('click', async () => {
      try {
        setCollabStatus('Initiating PayPal order with AUTHORIZE intent…');
        const orderData = await api(`/api/groups/${activeGroupID}/contributions/order`, {});
        setCollabStatus(`Order ${orderData.orderID} created! Authorizing hold…`);

        // Authorize with provider
        await api(`/api/groups/${activeGroupID}/contributions/authorize`, {});
        setCollabStatus('Payment authorized and held! Waiting for all members.');
        await refreshBookingView();
      } catch (err) {
        alert(err.message);
      }
    });
    box.appendChild(authBtn);
  } else if (share.state === 'AUTHORIZED') {
    box.innerHTML += '<p style="color:var(--accent); font-size:13px; font-weight:600;">✓ Your share is authorized and held in PayPal Sandbox.</p>';
  }

  // Void Button
  const voidBtn = document.createElement('button');
  voidBtn.type = 'button';
  voidBtn.className = 'btn btn-danger btn-sm';
  voidBtn.style.marginTop = '12px';
  voidBtn.textContent = 'Cancel Hold & Release Seats';
  voidBtn.addEventListener('click', async () => {
    if (!confirm('Cancel this booking and release held inventory?')) return;
    try {
      await api(`/api/groups/${activeGroupID}/booking/void`, {});
      setCollabStatus('Booking cancelled and inventory released.');
      await refreshBookingView();
    } catch (err) {
      alert(err.message);
    }
  });
  box.appendChild(voidBtn);

  panel.appendChild(box);
}

function renderFinalizationPanel(booking) {
  const panel = $('finalization-panel');
  panel.replaceChildren();

  if (booking.state === 'CONFIRMED') {
    panel.innerHTML = `
      <div style="background:rgba(16, 185, 129, 0.1); border:1px solid rgba(16, 185, 129, 0.3); padding:16px; border-radius:10px;">
        <h4 style="color:var(--accent); margin-bottom:4px;">Booking Confirmed &amp; Verified!</h4>
        <p class="fine">All captures completed. Your seats are booked and private tickets are issued.</p>
        <button id="open-ticket-btn-inline" type="button" class="btn btn-accent btn-sm" style="margin-top:10px;">View My Ticket &amp; Receipt</button>
      </div>
    `;
    setTimeout(() => {
      $('open-ticket-btn-inline')?.addEventListener('click', async () => {
        const ticket = await api(`/api/groups/${activeGroupID}/ticket`);
        showTicketModal(ticket);
      });
    }, 50);
    return;
  }

  const allAuthorized = (booking.rosterProgress || []).every((p) => p.hasAuthorized);

  if (booking.state === 'FINALIZING' || allAuthorized) {
    const finBtn = document.createElement('button');
    finBtn.type = 'button';
    finBtn.className = 'btn btn-accent';
    finBtn.textContent = '🚀 Finalize Group Booking & Issue Tickets';

    finBtn.addEventListener('click', async () => {
      try {
        setCollabStatus('Executing fenced sequential captures and ticket issuance…');
        await api(`/api/groups/${activeGroupID}/finalize`, {});
        setCollabStatus('All payments captured! Tickets issued successfully.');
        await refreshBookingView();
      } catch (err) {
        alert(err.message);
      }
    });

    panel.appendChild(finBtn);
  } else {
    panel.innerHTML = '<p class="fine">All members must authorize their individual shares before the booking can be finalized.</p>';
  }
}

function showTicketModal(ticket) {
  $('ticket-offer-title').textContent = ticket.title;
  $('ticket-schedule-time').textContent = new Date(ticket.scheduleTime).toLocaleString();
  $('ticket-seat-label').textContent = ticket.assignedResource || 'Assigned Place';
  $('ticket-alias-val').textContent = ticket.alias;
  $('ticket-code-display').textContent = ticket.ticketCode;
  $('ticket-paid-val').textContent = `$${ticket.shareValue}`;
  $('ticket-currency-val').textContent = ticket.currency;
  $('ticket-time-val').textContent = new Date(ticket.issuedAt * 1000).toLocaleString();
  $('ticket-modal').hidden = false;
}

// -------------------------------------------------------------
// WORKSHOP FLOW (PRESERVED SLICE 1)
// -------------------------------------------------------------
function renderWorkshops() {
  const container = $('workshops');
  if (!container || !config?.workshops) return;
  container.replaceChildren();
  for (const workshop of config.workshops) {
    const card = document.createElement('div');
    card.className = `workshop-card ${selectedWorkshop?.id === workshop.id ? 'selected' : ''}`;
    card.innerHTML = `
      <h2>${workshop.title}</h2>
      <p>${workshop.description}</p>
      <p class="fine">${new Date(workshop.startsAt).toLocaleString()}</p>
      <strong>$${workshop.value} ${workshop.currency}</strong>
    `;
    card.addEventListener('click', () => {
      selectedWorkshop = workshop;
      $('price').textContent = `$${workshop.value}`;
      renderWorkshops();
    });
    container.appendChild(card);
  }
}

// -------------------------------------------------------------
// INITIALIZATION
// -------------------------------------------------------------
document.addEventListener('DOMContentLoaded', async () => {
  setupTabs();
  setupCollabFlow();

  try {
    config = await api('/api/config');
    if (config.configured) {
      $('user-alias-badge').textContent = 'Session Ready';
    }
  } catch (err) {
    console.error('Config load failed:', err);
  }
});
