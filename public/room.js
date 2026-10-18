'use strict';

// Group coordination uses one browser identity. Fictional personas live in demo.js.
(function (root) {
  function cents(value) {
    if (value === '') return null;
    if (!/^\d+(\.\d{1,2})?$/.test(value)) throw new Error('Use a nonnegative budget with up to two decimal places.');
    const [whole, fraction = ''] = value.split('.');
    const result = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
    if (!Number.isSafeInteger(result)) throw new Error('Budget is too large.');
    return result;
  }
  const list = (value) => String(value || '').split(',').map((item) => item.trim()).filter(Boolean);
  function constraints(fields) {
    const time = {};
    for (const key of ['earliest', 'latest', 'finish_before']) if (fields[key]) time[key] = fields[key];
    return {budget_cents: cents(fields.budget), currency: 'USD', preferred_days: list(fields.days).map((day) => day.toLowerCase()),
      dates: list(fields.dates), timezone: fields.timezone, time_window: time,
      hard_constraints: [], soft_preferences: list(fields.preferences), clarifications: []};
  }
  function canApprove(booking, now = Date.now() / 1000) {
    return booking?.state === 'AWAITING_AUTHORIZATIONS' && booking.holdDeadline > now &&
      !!booking.myShare && booking.myShare.canAuthorize !== false &&
      !['AUTHORIZED', 'CAPTURED', 'VOIDED', 'REFUNDED'].includes(booking.myShare.state);
  }
  const helpers = {cents, constraints, canApprove};
  if (typeof module !== 'undefined' && module.exports) module.exports = helpers;
  if (typeof document === 'undefined') return;

  const $ = (id) => document.getElementById(id);
  const node = (tag, text, cls) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (cls) item.className = cls;
    return item;
  };
  const money = (value, currency = 'USD') => new Intl.NumberFormat(undefined, {style: 'currency', currency}).format(value / 100);
  const schedule = (value) => new Date(value).toLocaleString();
  const readable = (value) => String(value || 'Not started').replaceAll('_', ' ').toLowerCase();
  const closed = (booking) => ['CANCELLED', 'EXPIRED'].includes(booking?.state);
  const state = {group: null, booking: null, room: null, preference: null, offer: null, seats: [], quote: null,
    epoch: 0, sequence: 0, busy: false, approval: false, buttons: null, buttonKey: '', ticket: null,
    chatKey: '', poll: null, sdk: null, options: null, error: null,
    draft: null, edited: false, rescues: []};
  const path = (id, suffix = '') => `/api/groups/${encodeURIComponent(id)}${suffix}`;
  const current = (id, epoch) => state.group?.id === id && state.epoch === epoch;
  const locked = () => state.busy || state.approval;
  const frozen = () => state.booking?.hasBooking && !closed(state.booking);
  const status = (text, error = false) => {
    state.error = error ? text : null;
    $('collab-status-feed').textContent = text;
    $('collab-status-feed').classList.toggle('error', error);
    if (error) $('room-next-action').textContent = text;
  };
  const button = (text, action, cls = 'btn btn-secondary') => {
    const item = node('button', text, cls); item.type = 'button';
    item.addEventListener('click', action); return item;
  };
  async function run(task) {
    if (locked()) return;
    state.busy = true; state.error = null; state.sequence++; renderControls();
    try { await task(); } catch (error) { status(error.message, true); }
    finally { state.busy = false; renderControls(); }
  }
  async function closeButtons() {
    const epoch = state.epoch;
    const controls = state.buttons; state.buttons = null; state.buttonKey = '';
    if (controls) { try { await controls.close(); } catch {} }
    if (epoch === state.epoch) $('group-paypal-buttons').replaceChildren();
  }
  function bubble(parent, label, text, mine = false) {
    const item = node('div', undefined, `chat-msg ${mine ? 'chat-msg-own' : 'chat-msg-helper'}`);
    item.append(node('strong', label), node('p', text)); parent.append(item);
  }
  function renderPrivate() {
    const parent = $('chat-messages-container'), pref = state.preference || {};
    parent.replaceChildren();
    bubble(parent, 'YOUR PRIVATE CONCIERGE', 'Tell me your budget and schedule. Review the fields before confirming; your private preferences are not posted to the group.');
    if (pref.rawText) bubble(parent, 'YOU · PRIVATE', pref.rawText, true);
    const guide = pref.guidance;
    if (state.draft) {
      bubble(parent, 'YOUR PROPOSED CHANGE · NOT SAVED', 'Review these suggested edits below. Your current confirmed preferences stay in effect until you confirm this draft. Everyone else’s constraints remain unchanged.');
    } else if (guide) {
      bubble(parent, guide.label, [guide.summary, pref.isConfirmed ? 'Confirmed by you.' : guide.nextAction].filter(Boolean).join(' '));
      if (guide.clarifications?.length) bubble(parent, 'PLEASE REVIEW', guide.clarifications.join(' '));
      if (!pref.isConfirmed && guide.catalogSuggestions?.length) bubble(parent, 'YOUR CATALOG PREVIEW',
        guide.catalogSuggestions.slice(0, 2).map((offer) => `${offer.title} · ${schedule(offer.scheduleTime)}: ${offer.yourShareValue} USD for you. ${offer.reason}`).join('\n') + '\nThese previews do not establish group agreement.');
    }
    $('room-planning-mode').textContent = guide?.label || (state.options.getConfig().planningMode === 'gemini' ? 'Gemini available' : 'Local preference helper · no API key needed');
    $('room-preference-review').hidden = !pref.interpretation;
    const value = state.draft || pref.confirmedConstraints || pref.interpretation;
    if (!value) return;
    $('pref-budget').value = value.budget_cents == null ? '' : (value.budget_cents / 100).toFixed(2);
    $('pref-days').value = (value.preferred_days || []).join(', ');
    $('pref-dates').value = (value.dates || []).join(', ');
    $('pref-timezone').value = value.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
    for (const [id, key] of [['pref-earliest', 'earliest'], ['pref-latest', 'latest'], ['pref-finish', 'finish_before']]) $(id).value = value.time_window?.[key] || '';
    $('pref-soft').value = (value.soft_preferences || []).join(', ');
    $('pref-review-status').textContent = state.edited ? 'DRAFT CHANGE · CONFIRM TO SAVE' : pref.isConfirmed ? 'CONFIRMED BY YOU · edit to change' : 'REVIEW BEFORE CONFIRMING';
    $('pref-clarifications').textContent = [...(value.clarifications || []), ...(value.hard_constraints || [])].join(' · ');
    if (value.clarifications?.length) $('pref-advanced').open = true;
  }
  function renderChat() {
    const messages = state.room?.messages || [], key = JSON.stringify(messages);
    if (key === state.chatKey) return;
    state.chatKey = key;
    const feed = $('room-shared-feed'); feed.replaceChildren();
    if (!messages.length) feed.append(node('p', 'Say hello to your group. Shared messages are saved; your private concierge remains separate.', 'fine'));
    for (const message of messages) bubble(feed, message.isSelf ? 'YOU · SHARED' : message.alias, message.text, message.isSelf);
    if (state.room?.truncated) feed.prepend(node('p', 'Showing the latest 50 shared messages.', 'fine'));
  }
  function renderProgress() {
    const group = state.group, room = state.room || {}, booking = state.booking;
    $('room-group-title').textContent = group.name;
    $('room-group-desc').textContent = `${group.memberCount} ${group.memberCount === 1 ? 'person so far' : 'people'} · ${group.role === 'organizer' ? 'You organize this group' : 'You are a member'} · independent approval, exact shares.`;
    $('room-roster-count').textContent = `${group.memberCount} members`;
    $('copy-invite-btn').hidden = !group.inviteURL;
    const avatars = $('room-roster-avatars'); avatars.replaceChildren();
    for (const member of group.members || []) avatars.append(node('span', member.alias, 'room-member-pill'));
    $('room-readiness').textContent = `${room.confirmedCount || 0} of ${group.memberCount} preferences confirmed. Aliases and individual progress are shared only when opted in.`;
    const phase = booking?.state === 'CONFIRMED' ? 4 : frozen() ? 3 : group.memberCount > 1 ? 2 : 1;
    for (let i = 1; i <= 4; i++) {
      $(`room-step-${i}`).classList.toggle('is-current', i === phase);
      $(`room-step-${i}`).classList.toggle('is-complete', i < phase);
      $(`room-step-${i}`).setAttribute('aria-current', i === phase ? 'step' : 'false');
    }
    let next = room.nextAction || 'Describe your preferences, then review and confirm them.';
    if (group.memberCount < 2) next = 'Copy your invite and open it in a separate browser profile or send it to a friend. To rehearse alone, use the solo demo lab.';
    else if (booking?.state === 'CONFIRMED') next = 'All group captures are verified. Your private demonstration ticket is ready below.';
    else if (booking?.state === 'FINALIZING') next = group.role === 'organizer' ? 'All authorizations are ready. Complete the group capture pass.' : 'Your organizer can now complete group capture.';
    else if (booking?.recoveryRequired || booking?.state === 'RECOVERY_REQUIRED') next = 'A payment outcome is unresolved. Recheck your saved order; the organizer can reconcile recovery. Keep this reservation.';
    else if (canApprove(booking)) next = 'Review your exact share and cancellation terms, then approve your own hold in PayPal.';
    else if (booking?.myShare?.state === 'AUTHORIZED') next = 'Your hold is verified. Waiting for the remaining group authorizations; your ticket stays locked.';
    else if (state.quote) next = 'Review the exact roster shares. The organizer can now hold this selection for 15 minutes.';
    if (state.edited && !frozen()) next = 'You have an unsaved preference change. Review the fields and confirm before finding group matches.';
    $('room-next-action').textContent = state.error || next;
    const explanation = booking?.state === 'CONFIRMED' ? 'What happened: every required capture completed. Your private ticket is unlocked.' :
      booking?.recoveryRequired ? 'What is happening: a financial outcome needs checking. We keep the reservation intact while recovery is unresolved.' :
      frozen() ? 'What happened: places are reserved. Authorization holds funds; the organizer completes capture after everyone is verified.' :
      state.offer ? 'What happened: this experience satisfies the currently confirmed preferences. Review exact shares before reserving.' :
      'What is happening: you are planning together. Your private inputs become group constraints only after you confirm them. No payment has started.';
    $('room-explainer').textContent = explanation;
    $('room-next-button').textContent = group.memberCount < 2 ? 'Invite a friend ↗' : booking?.state === 'CONFIRMED' ? 'See my ticket ↓' : frozen() ? 'See my share ↓' : state.offer ? 'Review places ↓' : 'Review my plan ↓';
    $('room-planning-controls').hidden = frozen();
    $('room-profile-details').hidden = frozen();
  }
  function renderSeats() {
    const parent = $('interactive-seat-map'); parent.replaceChildren();
    const offer = state.offer;
    $('room-canvas-empty').hidden = !!offer || frozen();
    $('room-selection-tools').hidden = !offer;
    $('canvas-experience-sub').textContent = offer ? `${offer.title} · ${schedule(offer.scheduleTime)}` : frozen() ? `${state.booking.title} · ${state.booking.myShare?.assignedResource || 'saved reservation'}` : 'Confirm preferences and review a compatible match to choose seats or places.';
    if (!offer) { parent.append(node('p', 'Your shared experience will appear here.', 'fine')); renderQuote(); return; }
    $('seat-map-screen-text').textContent = offer.domain === 'movie' ? 'YOUR CINEMA SEATS' : 'YOUR ADVENTURE PLACES';
    const resources = [...(offer.resources || [])].sort((a, b) => String(a.row_label || a.row || '').localeCompare(String(b.row_label || b.row || '')) || (a.col_number || a.col) - (b.col_number || b.col));
    const columns = Math.max(1, Math.min(12, ...resources.map((r) => r.col_number || r.col || 1)));
    parent.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 1fr))`;
    for (const resource of resources) {
      const selected = state.seats.includes(resource.id), free = resource.state === 'FREE';
      const item = button(resource.label, () => {
        state.quote = null;
        state.seats = selected ? state.seats.filter((id) => id !== resource.id) : [...state.seats, resource.id];
        renderSeats(); renderControls();
      }, `seat-button${selected ? ' my-seat' : free ? '' : ' occupied'}`);
      item.disabled = locked() || frozen() || !free || state.group.role !== 'organizer';
      item.setAttribute('aria-pressed', String(selected));
      item.setAttribute('aria-label', `${resource.label}, ${selected ? 'selected' : free ? 'available' : 'unavailable'}`);
      parent.append(item);
    }
    renderQuote();
  }
  function renderQuote() {
    const saved = frozen() ? state.booking : null;
    $('quote-display-total').textContent = state.quote ? `${state.quote.totalValue} ${state.quote.currency}` : saved ? `${saved.totalValue} ${saved.currency}` : 'Get a server quote';
    $('quote-display-share').textContent = state.quote ? state.quote.shares.map((share) => `${share.shareValue} ${state.quote.currency}`).join(' + ') : saved ? `Saved reservation · your share: ${saved.myShare?.shareValue || 'unavailable'} ${saved.currency}` : 'Every remainder cent is included in the review.';
    const review = $('room-quote-breakdown'); review.replaceChildren();
    if (state.quote) {
      for (const share of state.quote.shares) {
        const member = state.group.members.find((item) => item.participantID === share.participantID);
        review.append(node('p', `${member?.alias || 'Member'}: ${share.shareValue} ${state.quote.currency}`));
      }
      review.append(node('p', state.quote.roundingRule, 'fine'));
    }
  }
  function renderControls() {
    if (!state.group) return;
    const booking = state.booking, organizer = state.group.role === 'organizer';
    $('btn-lock-freeze').disabled = locked() || frozen() || !organizer || !state.quote;
    $('room-quote-btn').disabled = locked() || frozen() || !organizer || !state.offer || state.seats.length !== state.group.memberCount;
    $('room-find-matches').disabled = locked() || frozen() || state.edited;
    $('room-rescue').disabled = locked() || frozen() || state.edited;
    $('room-rescue-ai').disabled = locked() || frozen() || state.edited;
    $('room-domain').disabled = locked() || frozen();
    for (const field of $('room-preference-review').querySelectorAll('input')) field.disabled = locked() || frozen();
    const recovery = document.querySelector('.recovery-details');
    if (recovery && booking?.recoveryRequired) recovery.open = true;
    $('chat-input-form').querySelector('button').disabled = locked() || frozen();
    $('room-preference-review').querySelector('button').disabled = locked() || frozen();
    $('room-shared-form').querySelector('button').disabled = locked();
    $('room-profile-form').querySelector('button').disabled = locked() || frozen();
    $('canvas-action-area').hidden = !booking?.hasBooking;
    $('room-payment-card').hidden = !booking?.hasBooking;
    $('canvas-finalize-btn').hidden = !organizer;
    $('canvas-finalize-btn').disabled = locked() || booking?.state !== 'FINALIZING';
    $('room-recover').hidden = !organizer;
    $('room-recover').disabled = locked() || !booking?.hasBooking || closed(booking) || booking.state === 'CONFIRMED';
    $('room-cancel').hidden = !organizer;
    $('room-cancel').disabled = locked() || !booking?.hasBooking || closed(booking) || booking.state === 'CONFIRMED';
    $('room-recheck').disabled = locked() || !booking?.hasBooking || closed(booking) || booking.state === 'CONFIRMED';
    $('room-payment-policy').hidden = !canApprove(booking);
    $('room-consent').disabled = locked();
    $('canvas-lifecycle-badge').textContent = readable(booking?.state || 'PLANNING');
    const roster = $('canvas-member-auth-list'); roster.replaceChildren();
    if (booking?.myShare) roster.append(node('p', `YOUR SHARE: ${booking.myShare.shareValue} ${booking.currency} · ${booking.myShare.assignedResource} · ${readable(booking.myShare.state)}`, 'room-own-share'));
    for (const item of booking?.rosterProgress || []) roster.append(node('p', `${item.alias}: ${readable(item.state)}${item.shareValue ? ` · ${item.shareValue} ${booking.currency}` : ''}`, 'fine'));
    $('room-payment-detail').textContent = [booking?.error, booking?.message, booking?.operationInProgress ? 'An operation is in progress. Wait before rechecking.' : '', booking?.myShare?.orderID ? `Your saved order: ${booking.myShare.orderID}` : ''].filter(Boolean).join(' · ');
    if (booking?.myShare?.consentGiven) $('room-consent').checked = true;
    renderProgress(); countdown();
    if (!state.approval) renderPayPal().catch((error) => status(error.message, true));
  }
  function countdown() {
    const booking = state.booking;
    const remaining = Math.max(0, Math.floor((booking?.holdDeadline || 0) - Date.now() / 1000));
    $('canvas-hold-countdown').textContent = booking?.state === 'CONFIRMED' ? 'Confirmed' : closed(booking) ? 'Closed' : !booking?.hasBooking ? 'No hold yet' : remaining ? `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')}` : 'Recheck required';
  }
  async function refresh() {
    if (!state.group) return;
    const id = state.group.id, epoch = state.epoch, sequence = ++state.sequence;
    const [group, booking, room] = await Promise.all([state.options.api(path(id)), state.options.api(path(id, '/booking')), state.options.api(path(id, '/room'))]);
    if (!current(id, epoch) || sequence !== state.sequence) return;
    if (group.memberCount !== state.group.memberCount) { state.quote = null; state.seats = []; renderSeats(); }
    state.group = group; state.booking = booking; state.room = room;
    if (frozen() && !state.offer) {
      state.offer = state.options.getOffers().find((offer) => offer.id === booking.offerID) || null;
      renderSeats();
    }
    renderChat(); renderControls();
    if (booking.state === 'CONFIRMED' && !state.ticket) await loadTicket();
    else if (booking.state !== 'CONFIRMED') { state.ticket = null; $('canvas-wallet-pass').hidden = true; }
    state.options.onGroup(group);
  }
  async function open(id, domain = 'movie') {
    const epoch = ++state.epoch;
    state.group = {id}; state.sequence++; state.approval = false;
    state.error = null;
    state.draft = null; state.edited = false; state.rescues = [];
    state.booking = state.room = state.preference = state.offer = state.quote = state.ticket = null;
    state.seats = []; state.chatKey = '';
    await closeButtons();
    $('canvas-wallet-pass').hidden = true; $('pass-inline-qr').replaceChildren();
    $('room-plan-results').replaceChildren(); $('room-shared-feed').replaceChildren();
    $('room-rescue-results').replaceChildren();
    $('room-domain').value = domain === 'excursion' ? 'excursion' : 'movie';
    $('room-consent').checked = false;
    const [group, booking, room, preference] = await Promise.all([
      state.options.api(path(id)), state.options.api(path(id, '/booking')), state.options.api(path(id, '/room')), state.options.api(path(id, '/preferences'))]);
    if (!current(id, epoch)) return null;
    state.group = group; state.booking = booking; state.room = room; state.preference = preference;
    if (frozen()) state.offer = state.options.getOffers().find((offer) => offer.id === booking.offerID) || null;
    $('room-alias').value = group.myProfile?.alias || '';
    $('room-share-progress').checked = !!group.myProfile?.shareProgress;
    $('chat-input-text').value = ''; $('room-shared-text').value = '';
    renderPrivate(); renderChat(); renderSeats(); renderControls();
    if (booking.state === 'CONFIRMED') await loadTicket();
    status('Your room is ready. Saved progress and shared messages refresh every five seconds.');
    history.replaceState(null, '', `/?group=${encodeURIComponent(id)}`);
    return group;
  }
  async function findMatches() {
    if (state.edited) throw new Error('Confirm your draft preferences before finding new matches.');
    const id = state.group.id, epoch = state.epoch;
    const plan = await state.options.api(path(id, `/plan?domain=${encodeURIComponent($('room-domain').value)}`));
    if (!current(id, epoch)) return;
    state.offer = state.quote = null; state.seats = []; renderSeats();
    const parent = $('room-plan-results'); parent.replaceChildren();
    if (plan.needsMembers) { parent.append(node('p', 'Invite at least one friend first. Prepare your own preferences while they join.')); return; }
    if (!plan.allConfirmed) { parent.append(node('p', `Waiting for confirmed preferences from: ${(plan.unconfirmedMembers || []).join(', ')}.`)); return; }
    parent.append(node('p', plan.matches?.length ? `${plan.matches.length} compatible experiences found.` : 'No compatible experience. Edit your own preferences or discuss another plan.'));
    if (plan.explanation) parent.append(node('p', plan.explanation, 'fine'));
    for (const conflict of plan.conflicts || []) parent.append(node('p', conflict.reason || conflict.type, 'fine'));
    for (const offer of plan.matches || []) {
      const card = node('article', undefined, 'room-match');
      card.append(node('h3', offer.title), node('p', schedule(offer.scheduleTime)), node('p', `Exact shares: ${offer.shareValues.join(' + ')} USD`, 'fine'));
      if (state.group.role === 'organizer') card.append(button('Review seats & shares', () => {
        state.offer = offer; state.seats = [...offer.proposedResourceIDs]; state.quote = null;
        renderSeats(); renderControls(); $('interactive-seat-map').scrollIntoView({block: 'nearest', behavior: 'auto'});
      }));
      else card.append(node('p', 'Your organizer selects the experience.', 'fine'));
      parent.append(card);
    }
  }
  function renderRescues(summary, ai = false) {
    const parent = $('room-rescue-results'); parent.replaceChildren(node('p', summary));
    $('rescue-mode').textContent = ai ? 'On-device AI ordered these verified options by your private vibe. Exact edits and eligibility were checked by server rules.' : 'Verified what-if calculations · not an AI-generated agreement. Review every proposed change.';
    for (const proposal of state.rescues.slice(0, 3)) {
      const card = node('article', undefined, 'rescue-option');
      card.append(node('h4', proposal.title), node('p', `${schedule(proposal.scheduleTime)} · Your exact share: ${proposal.ownShareValue} USD`));
      const changes = node('ul');
      for (const item of proposal.changes) changes.append(node('li', item.label));
      if (!proposal.changes.length) changes.append(node('li', 'Already fits every confirmed member. No preference change needed.'));
      card.append(changes);
      if (proposal.changes.length) card.append(button('Preview changes in my fields', () => {
        if (locked() || frozen()) return;
        state.draft = proposal.constraints; state.edited = true; state.quote = state.offer = null; state.seats = [];
        $('room-plan-results').replaceChildren(); renderPrivate(); renderSeats(); renderControls();
        $('room-preference-review').scrollIntoView({block: 'center', behavior: 'auto'});
        status('Draft preview only. Review the changed fields and confirm to save your own preferences.');
      }));
      else card.append(button('Find this in group matches', () => run(findMatches)));
      parent.append(card);
    }
  }
  async function rescue() {
    const id = state.group.id, epoch = state.epoch;
    const result = await state.options.api(path(id, '/rescue'), {domain: $('room-domain').value});
    if (!current(id, epoch)) return;
    state.rescues = result.proposals || []; renderRescues(result.summary);
    status(result.summary);
  }
  function sdk() {
    if (!state.options.getConfig().configured) return Promise.reject(new Error('Planning is ready. PayPal Sandbox credentials are needed for checkout.'));
    if (state.sdk) return state.sdk;
    state.sdk = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://www.paypal.com/sdk/js?' + new URLSearchParams({'client-id': state.options.getConfig().clientID, currency: 'USD', intent: 'authorize', components: 'buttons'});
      script.setAttribute('data-namespace', 'paypalGroup');
      script.onload = () => {
        if (root.paypalGroup?.Buttons) resolve(root.paypalGroup);
        else { state.sdk = null; reject(new Error('PayPal approval could not initialize. Refresh saved status to retry.')); }
      };
      script.onerror = () => { state.sdk = null; reject(new Error('PayPal approval could not load. Recheck your connection.')); };
      document.head.append(script);
    });
    return state.sdk;
  }
  async function renderPayPal() {
    const enabled = canApprove(state.booking) && $('room-consent').checked && state.options.getConfig().configured;
    const key = enabled ? `${state.group.id}:${state.booking.purchaseID}:${state.booking.myShare.state}:${state.epoch}` : '';
    if (key === state.buttonKey) return;
    const old = state.buttons;
    state.buttons = null; state.buttonKey = key;
    if (old) { try { await old.close(); } catch {} }
    if (state.buttonKey !== key) return;
    $('group-paypal-buttons').replaceChildren();
    if (!enabled) return;
    const id = state.group.id, epoch = state.epoch;
    let provider;
    try { provider = await sdk(); }
    catch (error) { if (current(id, epoch) && state.buttonKey === key) state.buttonKey = ''; throw error; }
    if (!current(id, epoch) || state.buttonKey !== key) return;
    const done = async () => { if (current(id, epoch)) { state.approval = false; await refresh(); } };
    state.buttons = provider.Buttons({
      style: {layout: 'vertical', shape: 'rect', label: 'paypal'},
      onClick(_data, actions) { return !locked() && current(id, epoch) && $('room-consent').checked && canApprove(state.booking) ? actions.resolve() : actions.reject(); },
      async createOrder() {
        if (!current(id, epoch) || !canApprove(state.booking) || !$('room-consent').checked) throw new Error('Review your saved share before approval.');
        state.approval = true; renderControls();
        try {
          await state.options.api(path(id, '/booking/consent'), {});
          const order = await state.options.api(path(id, '/contributions/order'), {});
          if (!order.orderID || !current(id, epoch)) throw new Error('Recheck the saved order before continuing.');
          return order.orderID;
        } catch (error) { await done(); throw error; }
      },
      async onApprove() {
        try {
          await state.options.api(path(id, '/contributions/authorize'), {});
          if (current(id, epoch)) status('Your authorization is verified. Tickets remain locked until all group captures complete.');
        } catch (error) { if (current(id, epoch)) status(`${error.message} Recheck your saved order.`, true); }
        finally { await done(); }
      },
      async onCancel() { if (current(id, epoch)) status('Approval closed. Your saved order remains available for recheck.'); await done(); },
      async onError(error) { if (current(id, epoch)) status(`${error.message || 'Approval interrupted.'} Recheck before another attempt.`, true); await done(); },
    });
    await state.buttons.render('#group-paypal-buttons');
  }
  async function loadTicket() {
    const id = state.group.id, epoch = state.epoch;
    const ticket = await state.options.api(path(id, '/ticket'));
    if (!current(id, epoch) || state.booking.state !== 'CONFIRMED') return;
    state.ticket = ticket;
    for (const [field, value] of Object.entries({'pass-title-val': ticket.title, 'pass-sub-val': schedule(ticket.scheduleTime), 'pass-seat-val': ticket.assignedResource, 'pass-inline-code': ticket.ticketCode, 'pass-holder-val': ticket.alias, 'pass-share-val': `${ticket.shareValue} ${ticket.currency}`, 'pass-capture-val': ticket.captureID})) $(field).textContent = value;
    const image = node('img'); image.src = path(id, '/ticket/qr'); image.alt = 'QR encoding of your private demonstration ticket reference';
    $('pass-inline-qr').replaceChildren(image); $('canvas-wallet-pass').hidden = false;
  }
  function init(options) {
    state.options = options;
    const form = (id, task) => $(id).addEventListener('submit', (event) => { event.preventDefault(); run(task); });
    form('chat-input-form', async () => {
      const id = state.group.id, epoch = state.epoch, rawText = $('chat-input-text').value.trim();
      if (!rawText) return;
      const preference = await options.api(path(id, '/preferences'), {rawText, userTz: Intl.DateTimeFormat().resolvedOptions().timeZone});
      if (!current(id, epoch)) return;
      state.preference = preference; state.offer = state.quote = null; state.seats = [];
      state.draft = null; state.edited = false; state.rescues = []; $('room-rescue-results').replaceChildren();
      $('room-plan-results').replaceChildren(); renderPrivate(); renderSeats();
      await refresh(); if (current(id, epoch)) status('Review and edit the extracted fields, then confirm your preferences.');
    });
    form('room-preference-review', async () => {
      const id = state.group.id, epoch = state.epoch;
      const value = constraints({budget: $('pref-budget').value, days: $('pref-days').value, dates: $('pref-dates').value,
        timezone: $('pref-timezone').value, earliest: $('pref-earliest').value, latest: $('pref-latest').value,
        finish_before: $('pref-finish').value, preferences: $('pref-soft').value});
      await options.api(path(id, '/preferences/confirm'), {confirmedConstraints: value});
      const preference = await options.api(path(id, '/preferences'));
      if (!current(id, epoch)) return;
      state.draft = null; state.edited = false; state.rescues = []; $('room-rescue-results').replaceChildren();
      state.preference = preference; renderPrivate(); await refresh();
      if (!current(id, epoch)) return;
      await findMatches();
      if (current(id, epoch)) status('Your preferences are confirmed. Group matches respect every confirmed member.');
    });
    form('room-shared-form', async () => {
      const id = state.group.id, epoch = state.epoch, text = $('room-shared-text').value.trim();
      if (!text) return;
      await options.api(path(id, '/messages'), {text});
      if (current(id, epoch)) { $('room-shared-text').value = ''; await refresh(); if (current(id, epoch)) status('Message shared with your group.'); }
    });
    form('room-profile-form', async () => {
      const id = state.group.id, epoch = state.epoch;
      await options.api(path(id, '/profile'), {alias: $('room-alias').value.trim(), shareProgress: $('room-share-progress').checked});
      if (current(id, epoch)) { await refresh(); if (current(id, epoch)) status('Your group profile and privacy choice are saved.'); }
    });
    $('room-find-matches').addEventListener('click', () => run(findMatches));
    $('room-rescue').addEventListener('click', () => run(rescue));
    $('room-rescue-ai').addEventListener('click', () => run(async () => {
      if (!root.GroupPayDiscover.aiReady()) { state.options.openDiscover(); $('scout-enable').focus(); return; }
      const id = state.group.id, epoch = state.epoch;
      if (!state.rescues.length) await rescue();
      if (!current(id, epoch) || !state.rescues.length) return;
      const ranked = await root.GroupPayDiscover.rankVerified(state.preference?.rawText || 'A good experience with friends', state.rescues);
      if (!current(id, epoch)) return;
      const order = new Map(ranked.map((item, index) => [item.id, index]));
      state.rescues.sort((a, b) => order.get(a.id) - order.get(b.id));
      renderRescues('Verified compromises, ordered by the vibe in your private description.', true);
    }));
    $('room-preference-review').addEventListener('input', () => {
      state.edited = true; state.quote = state.offer = null; state.seats = [];
      state.rescues = []; $('room-rescue-results').replaceChildren();
      $('pref-review-status').textContent = 'DRAFT CHANGE · CONFIRM TO SAVE';
      $('room-plan-results').replaceChildren(); renderSeats(); renderControls();
    });
    $('room-next-button').addEventListener('click', () => {
      if (state.group.memberCount < 2 && state.group.inviteURL) { $('copy-invite-btn').click(); return; }
      const id = state.booking?.state === 'CONFIRMED' ? 'canvas-wallet-pass' : frozen() ? 'room-payment-card' : state.offer ? 'room-selection-tools' : state.preference?.interpretation ? 'room-preference-review' : 'chat-input-form';
      $(id).scrollIntoView({block: 'center', behavior: 'auto'});
      if (id === 'chat-input-form') $('chat-input-text').focus();
    });
    $('room-domain').addEventListener('change', () => {
      state.offer = state.quote = null; state.seats = []; state.rescues = [];
      $('room-plan-results').replaceChildren(); $('room-rescue-results').replaceChildren();
      renderSeats(); renderControls();
    });
    $('room-quote-btn').addEventListener('click', () => run(async () => {
      const id = state.group.id, epoch = state.epoch, offer = state.offer, seats = [...state.seats];
      const quote = await options.api(path(id, '/quote'), {offerID: offer.id, resourceIDs: seats});
      if (!current(id, epoch) || state.offer !== offer || seats.join() !== state.seats.join()) return;
      state.quote = quote; renderQuote(); status('Review the exact server quote before holding seats.');
    }));
    $('btn-lock-freeze').addEventListener('click', () => run(async () => {
      if (!state.quote) throw new Error('Get a fresh server quote first.');
      const id = state.group.id, epoch = state.epoch;
      await options.api(path(id, '/freeze'), {offerID: state.offer.id, resourceIDs: state.seats});
      if (current(id, epoch)) { await refresh(); if (current(id, epoch)) { renderSeats(); status('Places held for 15 minutes. Everyone approves only their own share.'); } }
    }));
    for (const [id, suffix] of [['room-recheck', '/contributions/reconcile'], ['room-recover', '/recover'], ['room-cancel', '/booking/void'], ['canvas-finalize-btn', '/finalize']]) $(id).addEventListener('click', () => run(async () => {
      if (id === 'room-cancel' && !root.confirm('Cancel this reservation? Existing payment holds or captures may need void or refund recovery.')) return;
      const gid = state.group.id, epoch = state.epoch;
      try { await options.api(path(gid, suffix), {}); }
      finally { if (current(gid, epoch)) await refresh(); }
      if (current(gid, epoch)) status('Saved status updated. Review the next action and any pending payment outcomes.');
    }));
    $('room-refresh').addEventListener('click', () => run(refresh));
    $('room-consent').addEventListener('change', () => renderPayPal().catch((error) => status(error.message, true)));
    $('copy-invite-btn').addEventListener('click', () => run(async () => {
      try { await navigator.clipboard.writeText(state.group.inviteURL); status('Invite copied. Each participant needs a separate browser profile or device.'); }
      catch { $('room-invite-link').value = state.group.inviteURL; $('room-invite-link').hidden = false; $('room-invite-link').select(); status('Copy the selected invite manually.'); }
    }));
    document.querySelectorAll('.chip-preset').forEach((chip) => chip.addEventListener('click', () => { $('chat-input-text').value = chip.dataset.text; $('chat-input-text').focus(); }));
    $('btn-download-pass').addEventListener('click', () => {
      if (!state.ticket) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify({scope: 'fictional-private-ticket', ...state.ticket}, null, 2)], {type: 'application/json'}));
      const link = node('a'); link.href = url; link.download = 'grouppay-ticket.json'; link.click(); URL.revokeObjectURL(url);
    });
    $('btn-print-pass').addEventListener('click', () => root.print());
    $('btn-scan-validator').addEventListener('click', () => {
      if (!state.ticket) return;
      $('qr-validator-modal').hidden = false; $('ticket-check-code').value = '';
      $('ticket-check-result').textContent = 'Paste your ticket code. This checks your owned record; it does not redeem venue admission.';
      $('ticket-check-code').focus();
    });
    form('ticket-check-form', async () => {
      const id = state.group.id, epoch = state.epoch;
      const result = await options.api(path(id, '/ticket/check'), {ticketCode: $('ticket-check-code').value});
      if (current(id, epoch)) $('ticket-check-result').textContent = result.valid ? `Verified against your confirmed private ticket: ${result.offeringTitle} · ${result.assignedResource}. No admission was redeemed.` : 'This code does not match your confirmed private ticket.';
    });
    $('close-validator-modal-btn').addEventListener('click', () => { $('qr-validator-modal').hidden = true; $('btn-scan-validator').focus(); });
    if (!state.poll) {
      state.poll = setInterval(() => {
        if (state.group && !locked() && !document.hidden && options.isVisible()) refresh().catch((error) => status(error.message, true));
      }, 5000);
      setInterval(() => { if (state.group && !document.hidden) countdown(); }, 1000);
    }
  }
  root.GroupPayRoom = {init, open, refresh, helpers};
})(typeof window === 'undefined' ? globalThis : window);
