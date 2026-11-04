'use strict';

// Informal personal expense splitting. A private ledger between named people, not PayPal
// payment state: nothing here owns consent, prices, inventory or tickets. Receipt scanning
// is server-local Hugging Face inference; its output is an editable, unsaved preview.
(function (root) {
  const CATEGORIES = ['food', 'travel', 'rent', 'entertainment', 'shopping', 'other'];
  const CATEGORY_LABEL = {food: 'Food', travel: 'Travel', rent: 'Rent', entertainment: 'Entertainment', shopping: 'Shopping', other: 'Other'};
  // Geometric text glyphs (with explicit text-presentation selectors) so no platform substitutes an emoji.
  const CATEGORY_ICON = {food: '\u25C9', travel: '\u2708\uFE0E', rent: '\u2302', entertainment: '\u266A', shopping: '\u25A3', other: '\u25C7'};
  // Inline stroked bell so reminder buttons keep the app's icon language instead of an emoji glyph.
  const BELL_ICON = '<svg class="icon-bell" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M18 8.5a6 6 0 1 0-12 0c0 5-2 6.5-2 6.5h16s-2-1.5-2-6.5"/><path d="M13.7 19a2 2 0 0 1-3.4 0"/></svg>';

  function cents(value) {
    const trimmed = String(value || '').trim();
    if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) throw new Error('Enter a positive amount with up to two decimal places.');
    const [whole, fraction = ''] = trimmed.split('.');
    const result = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
    if (!Number.isSafeInteger(result) || result <= 0) throw new Error('Enter an amount greater than zero.');
    return result;
  }

  function money(minor, currency = 'USD') {
    return new Intl.NumberFormat(undefined, {style: 'currency', currency}).format((minor || 0) / 100);
  }

  // Mirrors app/shared/storage.py's split_equal_cents: largest-remainder-first, exact sum.
  function splitEqualCents(totalMinor, names) {
    const n = names.length;
    const base = Math.floor(totalMinor / n);
    const remainder = totalMinor % n;
    const result = {};
    names.forEach((name, i) => { result[name] = base + (i < remainder ? 1 : 0); });
    return result;
  }

  function mount(container, ctx) {
    if (!container) return null;
    const api = ctx.api;
    const escapeHtml = ctx.escapeHtml || ((s) => String(s === null || s === undefined ? '' : s));
    const getCsrfToken = ctx.getCsrfToken || (() => '');

    const state = {
      view: 'dashboard', groups: [], friends: [], splits: [], subscriptions: [], analytics: null,
      profile: {displayName: '', upiID: ''}, busy: false, loaded: false, error: '', notice: '',
      activityGroup: 'ALL', modal: null, draft: null, saving: false,
    };

    function $$(selector) { return container.querySelector(selector); }

    async function refreshAll() {
      state.busy = true; state.error = ''; render();
      try {
        const [groups, friends, splits, subs, analytics, profile] = await Promise.all([
          api('/api/expenses/groups'), api('/api/expenses/friends'), api('/api/expenses/splits'),
          api('/api/expenses/subscriptions'), api('/api/expenses/analytics'), api('/api/expenses/profile'),
        ]);
        state.groups = groups.groups; state.friends = friends.friends; state.splits = splits.splits;
        state.subscriptions = subs.subscriptions; state.analytics = analytics.analytics; state.profile = profile.profile;
        state.loaded = true;
      } catch (err) {
        state.error = err.message;
      }
      state.busy = false;
      render();
    }

    async function refreshSplitsAndAnalytics() {
      try {
        const [splits, analytics] = await Promise.all([api('/api/expenses/splits'), api('/api/expenses/analytics')]);
        state.splits = splits.splits; state.analytics = analytics.analytics;
      } catch (err) { state.error = err.message; }
    }

    // ------------------------------------------------- reminders (local only; never touches payment/consent state)
    async function copyText(text) {
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
          return true;
        }
      } catch { /* fall through to legacy path */ }
      try {
        const ta = document.createElement('textarea');
        ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta); ta.focus(); ta.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        return ok;
      } catch { return false; }
    }

    function friendWhatsappDigits(name) {
      const friend = state.friends.find((f) => f.name.toLowerCase() === name.toLowerCase());
      const digits = friend && friend.whatsapp ? friend.whatsapp.replace(/[^\d]/g, '') : '';
      return digits.length >= 8 ? digits : '';
    }

    async function remindShare(split, share) {
      const message = 'Hi ' + share.name + '! Quick reminder \u2014 you owe ' + money(share.amountMinor, split.currency) + ' for "' + split.title + '" from our GroupPay split. Thanks!';
      const digits = friendWhatsappDigits(share.name);
      if (digits) {
        window.open('https://wa.me/' + digits + '?text=' + encodeURIComponent(message), '_blank', 'noopener,noreferrer');
        state.notice = 'Opened WhatsApp to remind ' + share.name + '.';
      } else {
        const copied = await copyText(message);
        state.notice = copied ? ('Reminder copied \u2014 send it to ' + share.name + ' however you reach them.') : message;
      }
      render();
    }

    async function remindAllPending(split) {
      const pending = split.shares.filter((s) => !s.isPayer && !s.settled);
      if (!pending.length) return;
      const lines = pending.map((s) => '- ' + s.name + ': ' + money(s.amountMinor, split.currency)).join('\n');
      const message = 'Reminder for "' + split.title + '":\n' + lines + '\nStill pending: ' + money(split.pendingMinor, split.currency);
      const copied = await copyText(message);
      state.notice = copied ? 'Reminder summary copied \u2014 paste it wherever your group chats.' : message;
      render();
    }

    // ----------------------------------------------------------- new-split draft
    function openSplitModal() {
      state.modal = 'split';
      state.notice = '';
      state.draft = {
        title: '', category: 'food', currency: 'USD', groupId: '',
        total: '', selected: [], scanBusy: false, scanError: '', scanInfo: '', receiptMeta: null, formError: '',
        scanStatus: null, scanPreviewUrl: '',
      };
      render();
      api('/api/expenses/scan-status').then((status) => { if (state.draft) { state.draft.scanStatus = status; render(); } }).catch(() => {});
    }

    function syncSplitDraftFromForm() {
      if (!state.draft) return;
      const title = $$('#exp-split-title'); if (title) state.draft.title = title.value;
      const total = $$('#exp-split-total'); if (total) state.draft.total = total.value;
      const group = $$('#exp-split-group'); if (group) state.draft.groupId = group.value;
      const category = $$('#exp-split-category'); if (category) state.draft.category = category.value;
    }

    function participantNames() {
      const you = state.profile.displayName || 'You';
      return [you, ...state.draft.selected];
    }

    // Object URLs for the local receipt preview are revoked whenever the draft is replaced or closed.
    function releaseScanPreview() {
      if (state.draft && state.draft.scanPreviewUrl) {
        try { URL.revokeObjectURL(state.draft.scanPreviewUrl); } catch { /* already revoked */ }
        state.draft.scanPreviewUrl = '';
      }
    }

    function closeModal() {
      releaseScanPreview();
      state.modal = null;
      state.draft = null;
    }

    async function handleScan(file) {
      syncSplitDraftFromForm();
      releaseScanPreview();
      try { state.draft.scanPreviewUrl = URL.createObjectURL(file); } catch { state.draft.scanPreviewUrl = ''; }
      state.draft.scanBusy = true; state.draft.scanError = ''; state.draft.scanInfo = ''; render();
      try {
        const formData = new FormData();
        formData.append('receipt', file);
        const response = await fetch('/api/expenses/scan-receipt', {
          method: 'POST', credentials: 'same-origin', cache: 'no-store',
          headers: {'X-CSRF-Token': getCsrfToken()}, body: formData,
        });
        let data;
        try { data = await response.json(); } catch { throw new Error('Server response could not be parsed.'); }
        if (!response.ok) throw new Error(data.message || data.error || 'Receipt scan failed.');
        if (data.parsed && data.fields) {
          const fields = data.fields;
          if (fields.merchant) state.draft.title = fields.merchant;
          if (fields.category) state.draft.category = fields.category;
          if (fields.currency) state.draft.currency = fields.currency;
          if (typeof fields.total === 'number') state.draft.total = fields.total.toFixed(2);
          state.draft.receiptMeta = fields;
          state.draft.scanInfo = 'Local AI suggested these fields from the photo. Review every value before saving — nothing is saved yet.';
        } else {
          state.draft.scanError = 'The local model could not read a clear total from this photo. Enter the details manually.';
        }
      } catch (err) {
        state.draft.scanError = err.message;
      }
      state.draft.scanBusy = false;
      render();
    }

    async function saveSplit() {
      syncSplitDraftFromForm();
      state.draft.formError = '';
      let totalMinor;
      try { totalMinor = cents(state.draft.total); }
      catch (err) { state.draft.formError = err.message; render(); return; }
      if (!state.draft.title.trim()) { state.draft.formError = 'Give this split a title.'; render(); return; }
      const names = participantNames();
      const uniqueNames = new Set(names.map((n) => n.toLowerCase()));
      if (uniqueNames.size !== names.length) { state.draft.formError = 'Each person in a split needs a distinct name.'; render(); return; }
      const amounts = splitEqualCents(totalMinor, names);
      const payer = names[0];
      const shares = names.map((name) => ({name, amountMinor: amounts[name], isPayer: name === payer}));
      state.saving = true; render();
      try {
        await api('/api/expenses/splits', {
          title: state.draft.title.trim(), category: state.draft.category, currency: state.draft.currency,
          shares, groupID: state.draft.groupId || null,
          source: state.draft.receiptMeta ? 'scan' : 'manual', receiptMeta: state.draft.receiptMeta,
        });
        closeModal();
        state.notice = 'Split saved.';
        state.saving = false;
        await refreshAll();
        return;
      } catch (err) {
        state.draft.formError = err.message;
      }
      state.saving = false;
      render();
    }

    // ----------------------------------------------------------- subscription draft
    function openSubscriptionModal() {
      state.modal = 'subscription';
      state.draft = {name: '', monthlyAmount: '', billingDay: '1', participants: [], formError: ''};
      render();
    }

    function syncSubscriptionDraftFromForm() {
      if (!state.draft) return;
      const name = $$('#exp-sub-name'); if (name) state.draft.name = name.value;
      const amount = $$('#exp-sub-amount'); if (amount) state.draft.monthlyAmount = amount.value;
      const day = $$('#exp-sub-day'); if (day) state.draft.billingDay = day.value;
      state.draft.participants.forEach((p, i) => {
        const nameField = $$(`#exp-sub-p-name-${i}`); if (nameField) p.name = nameField.value;
        const waField = $$(`#exp-sub-p-wa-${i}`); if (waField) p.whatsapp = waField.value;
      });
    }

    async function saveSubscription() {
      syncSubscriptionDraftFromForm();
      state.draft.formError = '';
      let monthlyMinor;
      try { monthlyMinor = cents(state.draft.monthlyAmount); }
      catch (err) { state.draft.formError = err.message; render(); return; }
      if (!state.draft.name.trim()) { state.draft.formError = 'Give this subscription a name.'; render(); return; }
      const billingDay = Number(state.draft.billingDay);
      if (!Number.isInteger(billingDay) || billingDay < 1 || billingDay > 28) {
        state.draft.formError = 'Billing day must be between 1 and 28.'; render(); return;
      }
      const participants = state.draft.participants.filter((p) => p.name.trim()).map((p) => ({name: p.name.trim(), whatsapp: p.whatsapp.trim()}));
      state.saving = true; render();
      try {
        await api('/api/expenses/subscriptions', {
          name: state.draft.name.trim(), monthlyAmountMinor: monthlyMinor, billingDay, currency: 'USD', participants,
        });
        state.modal = null; state.draft = null;
        state.notice = 'Subscription reminder saved. Nothing is charged automatically.';        state.saving = false;
        await refreshAll();
        return;
      } catch (err) {
        state.draft.formError = err.message;
      }
      state.saving = false;
      render();
    }

    // ----------------------------------------------------------- actions
    async function onClick(event) {
      const button = event.target.closest('[data-action]');
      if (!button) return;
      const action = button.dataset.action;
      try {
        if (action === 'nav') { state.view = button.dataset.view; state.notice = ''; render(); }
        else if (action === 'new-split') { openSplitModal(); }
        else if (action === 'new-subscription') { openSubscriptionModal(); }
        else if (action === 'close-modal') { closeModal(); render(); }
        else if (action === 'toggle-participant') {
          syncSplitDraftFromForm();
          const name = button.dataset.name;
          const i = state.draft.selected.indexOf(name);
          if (i >= 0) state.draft.selected.splice(i, 1); else state.draft.selected.push(name);
          render();
        }
        else if (action === 'trigger-scan') { $$('#exp-scan-input')?.click(); }
        else if (action === 'save-split') { await saveSplit(); }
        else if (action === 'save-subscription') { await saveSubscription(); }
        else if (action === 'add-sub-participant') {
          syncSubscriptionDraftFromForm();
          state.draft.participants.push({name: '', whatsapp: ''});
          render();
        }
        else if (action === 'remove-sub-participant') {
          syncSubscriptionDraftFromForm();
          state.draft.participants.splice(Number(button.dataset.index), 1);
          render();
        }
        else if (action === 'delete-friend') {
          button.disabled = true;
          const result = await api('/api/expenses/friends/' + encodeURIComponent(button.dataset.id) + '/delete', {});
          state.friends = result.friends; render();
        }
        else if (action === 'delete-subscription') {
          button.disabled = true;
          const result = await api('/api/expenses/subscriptions/' + encodeURIComponent(button.dataset.id) + '/delete', {});
          state.subscriptions = result.subscriptions; render();
        }
        else if (action === 'toggle-settle') {
          button.disabled = true;
          await api(`/api/expenses/splits/${button.dataset.split}/settle`, {
            shareID: button.dataset.share, settled: button.dataset.settled !== 'true',
          });
          await refreshSplitsAndAnalytics();
          render();
        }
        else if (action === 'remind-share') {
          const split = state.splits.find((s) => s.id === button.dataset.split);
          const share = split && split.shares.find((sh) => sh.id === button.dataset.share);
          if (split && share) await remindShare(split, share);
        }
        else if (action === 'remind-split') {
          const split = state.splits.find((s) => s.id === button.dataset.split);
          if (split) await remindAllPending(split);
        }
        else if (action === 'filter-activity-group') { state.activityGroup = button.dataset.group; state.view = 'activity'; render(); }
      } catch (err) {
        state.error = err.message;
        render();
      }
    }

    async function onSubmit(event) {
      const form = event.target.closest('form');
      if (!form) return;
      event.preventDefault();
      try {
        if (form.id === 'exp-friend-form') {
          const name = $$('#exp-friend-name').value.trim();
          const upiID = $$('#exp-friend-upi').value.trim();
          const whatsapp = $$('#exp-friend-whatsapp').value.trim();
          if (!name) return;
          const result = await api('/api/expenses/friends', {name, upiID, whatsapp});
          state.friends = result.friends;
          form.reset();
          render();
        } else if (form.id === 'exp-profile-form') {
          const displayName = $$('#exp-profile-name').value.trim();
          const upiID = $$('#exp-profile-upi').value.trim();
          const result = await api('/api/expenses/profile', {displayName, upiID});
          state.profile = result.profile;
          state.notice = 'Account details saved.';
          render();
        }
      } catch (err) {
        state.error = err.message;
        render();
      }
    }

    async function onFileChange(event) {
      const input = event.target.closest('#exp-scan-input');
      if (!input || !input.files || !input.files[0]) return;
      const file = input.files[0];
      input.value = '';
      await handleScan(file);
    }

    container.addEventListener('click', onClick);
    container.addEventListener('submit', onSubmit);
    container.addEventListener('change', onFileChange);

    // ----------------------------------------------------------- rendering
    function pendingForGroup(groupId) {
      return state.splits.filter((s) => s.groupID === groupId).reduce((sum, s) => sum + s.pendingMinor, 0);
    }

    function renderDashboard() {
      const totalPending = state.splits.reduce((sum, s) => sum + s.pendingMinor, 0);
      const cards = state.groups.map((g) => `
        <button type="button" class="exp-group-card" data-action="filter-activity-group" data-group="${g.id === null ? 'none' : escapeHtml(g.id)}">
          <strong>${escapeHtml(g.name)}</strong>
          <span class="fine">${g.splitCount} split${g.splitCount === 1 ? '' : 's'}</span>
          <span class="exp-pending">${money(pendingForGroup(g.id))} pending</span>
        </button>`).join('');
      return `
        <div class="exp-summary-row">
          <div class="exp-summary-card"><span class="fine">Tracked across all your splits</span><strong>${money(state.analytics ? state.analytics.totalMinor : 0)}</strong></div>
          <div class="exp-summary-card"><span class="fine">Still pending settlement</span><strong>${money(totalPending)}</strong></div>
          <div class="exp-summary-card"><span class="fine">Splits logged</span><strong>${state.analytics ? state.analytics.splitCount : 0}</strong></div>
        </div>
        <h2 class="exp-subheading">Groups</h2>
        <div class="exp-group-grid">${cards || '<p class="fine">No groups yet. Splits with no group show up as Individual expenses.</p>'}</div>`;
    }

    function renderShareRow(split, share) {
      const toggleable = !share.isPayer;
      const canRemind = toggleable && !share.settled;
      const initial = escapeHtml((String(share.name).trim().charAt(0) || '?').toUpperCase());
      return `
        <li class="exp-share-row ${share.settled ? 'exp-settled' : ''}">
          <span class="exp-share-who">
            <span class="exp-avatar">${initial}</span>
            <span>${escapeHtml(share.name)}</span>
            ${share.isPayer ? '<span class="badge">paid</span>' : ''}
          </span>
          <span class="exp-share-amount">${money(share.amountMinor, split.currency)}</span>
          <span class="exp-share-actions">
            ${canRemind ? `<button type="button" class="btn btn-quiet exp-remind-btn" data-action="remind-share" data-split="${split.id}" data-share="${share.id}">${BELL_ICON}Remind</button>` : ''}
            ${toggleable ? `<button type="button" class="btn btn-quiet" data-action="toggle-settle" data-split="${split.id}" data-share="${share.id}" data-settled="${share.settled}">${share.settled ? 'Mark unsettled' : 'Mark settled'}</button>` : '<span class="fine">Always settled</span>'}
          </span>
        </li>`;
    }

    function renderSplitCard(split) {
      const groupName = split.groupID === null ? 'Individual' : (state.groups.find((g) => g.id === split.groupID)?.name || 'Group');
      const icon = CATEGORY_ICON[split.category] || CATEGORY_ICON.other;
      return `
        <div class="exp-split-card ${split.allSettled ? 'is-settled' : 'is-pending'}">
          <div class="exp-split-head">
            <div class="exp-split-ident">
              <span class="exp-cat-icon exp-cat-${escapeHtml(split.category)}" aria-hidden="true">${icon}</span>
              <div>
                <strong>${escapeHtml(split.title)}</strong>
                <span class="fine">${CATEGORY_LABEL[split.category] || split.category} &middot; ${groupName} &middot; ${new Date(split.createdAt * 1000).toLocaleDateString()}</span>
              </div>
            </div>
            <div class="exp-split-total">
              <span class="exp-split-amount">${money(split.totalMinor, split.currency)}</span>
              ${split.allSettled ? '<span class="badge badge-success">All settled</span>' : `<span class="badge badge-gold">${money(split.pendingMinor, split.currency)} pending</span>`}
              ${!split.allSettled ? `<button type="button" class="btn btn-outline exp-remind-all-btn" data-action="remind-split" data-split="${split.id}">${BELL_ICON}Remind all pending</button>` : ''}
            </div>
          </div>
          <ul class="exp-share-list">${split.shares.map((s) => renderShareRow(split, s)).join('')}</ul>
        </div>`;
    }

    function renderActivity() {
      const filtered = state.activityGroup === 'ALL' ? state.splits
        : state.splits.filter((s) => (state.activityGroup === 'none' ? s.groupID === null : s.groupID === state.activityGroup));
      const pills = [{key: 'ALL', label: 'All'}, {key: 'none', label: 'Individual'},
        ...state.groups.filter((g) => g.id !== null).map((g) => ({key: g.id, label: g.name}))];
      return `
        <div class="filter-row exp-filter-row">${pills.map((p) => `
          <button type="button" class="filter-pill ${state.activityGroup === p.key ? 'active' : ''}" data-action="filter-activity-group" data-group="${escapeHtml(p.key)}">${escapeHtml(p.label)}</button>`).join('')}
        </div>
        <div class="exp-split-list">${filtered.length ? filtered.map(renderSplitCard).join('') : '<p class="fine">No splits yet here. Use + New split to log one.</p>'}</div>`;
    }

    function renderFriends() {
      const rows = state.friends.map((f) => `
        <li class="exp-friend-row">
          <span><strong>${escapeHtml(f.name)}</strong>${f.upiID ? ` <span class="fine">${escapeHtml(f.upiID)}</span>` : ''}${f.whatsapp ? ` <span class="fine">${escapeHtml(f.whatsapp)}</span>` : ''}</span>
          <button type="button" class="btn btn-quiet" data-action="delete-friend" data-id="${escapeHtml(f.id)}">Remove</button>
        </li>`).join('');
      return `
        <h2 class="exp-subheading">Friends</h2>
        <form id="exp-friend-form" class="exp-inline-form">
          <input id="exp-friend-name" type="text" placeholder="Name" maxlength="80" required>
          <input id="exp-friend-upi" type="text" placeholder="UPI ID (optional)" maxlength="80">
          <input id="exp-friend-whatsapp" type="text" placeholder="WhatsApp (optional)" maxlength="40">
          <button type="submit" class="btn btn-primary">Add friend</button>
        </form>
        <ul class="exp-friend-list">${rows || '<p class="fine">No friends saved yet.</p>'}</ul>`;
    }

    function renderSubscriptions() {
      const cards = state.subscriptions.map((s) => `
        <div class="exp-sub-card">
          <div>
            <strong>${escapeHtml(s.name)}</strong>
            <span class="fine">${money(s.monthlyAmountMinor, s.currency)} / month &middot; billed on day ${s.billingDay}</span>
            <span class="fine">${s.participants.map((p) => escapeHtml(p.name)).join(', ') || 'Just you'}</span>
          </div>
          <button type="button" class="btn btn-quiet" data-action="delete-subscription" data-id="${escapeHtml(s.id)}">Remove</button>
        </div>`).join('');
      return `
        <div class="section-header"><h2 class="exp-subheading">Subscriptions</h2>
          <button type="button" class="btn btn-outline" data-action="new-subscription">+ Add subscription</button></div>
        <p class="fine">Reminders only. Nothing here charges anyone automatically.</p>
        <div class="exp-sub-grid">${cards || '<p class="fine">No shared subscriptions yet.</p>'}</div>`;
    }

    function renderAnalytics() {
      const a = state.analytics || {totalMinor: 0, byCategory: {}, byMonth: {}, splitCount: 0};
      const maxCategory = Math.max(1, ...Object.values(a.byCategory));
      const categoryRows = CATEGORIES.filter((c) => a.byCategory[c]).map((c) => `
        <li><span>${CATEGORY_LABEL[c]}</span>
          <div class="exp-bar-track"><div class="exp-bar-fill" style="width:${(a.byCategory[c] / maxCategory) * 100}%"></div></div>
          <span>${money(a.byCategory[c])}</span></li>`).join('');
      const monthRows = Object.entries(a.byMonth).map(([month, amount]) => `<li><span>${escapeHtml(month)}</span><span>${money(amount)}</span></li>`).join('');
      return `
        <h2 class="exp-subheading">Analytics</h2>
        <p class="fine">Totals across the splits you created. Not a financial or tax record.</p>
        <h3 class="exp-mini-heading">By category</h3>
        <ul class="exp-bar-list">${categoryRows || '<p class="fine">Nothing logged yet.</p>'}</ul>
        <h3 class="exp-mini-heading">By month</h3>
        <ul class="exp-month-list">${monthRows || '<p class="fine">Nothing logged yet.</p>'}</ul>`;
    }

    function renderAccount() {
      return `
        <h2 class="exp-subheading">Account</h2>
        <p class="fine">Shown to people you split with here. Not your PayPal identity.</p>
        <form id="exp-profile-form" class="exp-form-grid">
          <label>Display name<input id="exp-profile-name" type="text" maxlength="80" value="${escapeHtml(state.profile.displayName)}"></label>
          <label>UPI ID<input id="exp-profile-upi" type="text" maxlength="80" value="${escapeHtml(state.profile.upiID)}"></label>
          <button type="submit" class="btn btn-primary">Save</button>
        </form>`;
    }

    function renderSplitModal() {
      const d = state.draft;
      const groupOptions = state.groups.filter((g) => g.id !== null).map((g) => `<option value="${escapeHtml(g.id)}" ${d.groupId === g.id ? 'selected' : ''}>${escapeHtml(g.name)}</option>`).join('');
      const friendChecks = state.friends.map((f) => `
        <label class="exp-check"><input type="checkbox" data-action="toggle-participant" data-name="${escapeHtml(f.name)}" ${d.selected.includes(f.name) ? 'checked' : ''}><span class="exp-avatar">${escapeHtml((f.name.trim().charAt(0) || '?').toUpperCase())}</span>${escapeHtml(f.name)}</label>`).join('');
      const you = state.profile.displayName || 'You';
      const names = [you, ...d.selected];
      let previewLine = '';
      try {
        const totalMinor = d.total ? cents(d.total) : 0;
        if (totalMinor > 0) {
          const amounts = splitEqualCents(totalMinor, names);
          previewLine = `${escapeHtml(you)} pays. Split equally: ${names.map((n) => `${escapeHtml(n)} ${money(amounts[n])}`).join(', ')}.`;
        }
      } catch { /* shown via formError on save */ }
      const scanStatus = d.scanStatus;
      const scanDisabledNote = scanStatus && !scanStatus.available ? `<p class="fine exp-warn">Receipt model is not ready on this server (${escapeHtml(scanStatus.model || 'model')}). Enter details manually.</p>` : '';
      return `
        <div class="modal-backdrop" id="exp-split-modal-backdrop">
          <div class="modal-card modal-card-wide">
            <div class="modal-header">
              <div class="split-modal-title">
                <span class="badge badge-gold">NEW LEDGER ENTRY</span>
                <h2>New split</h2>
              </div>
              <button type="button" class="modal-close-btn" data-action="close-modal">&times;</button></div>
            <div class="modal-body">
              ${d.formError ? `<p class="exp-error">${escapeHtml(d.formError)}</p>` : ''}
              ${d.scanInfo ? `<p class="exp-notice">${escapeHtml(d.scanInfo)}</p>` : ''}
              ${d.scanError ? `<p class="exp-warn">${escapeHtml(d.scanError)}</p>` : ''}
              ${scanDisabledNote}
              <div class="exp-scan-card">
                <div class="exp-scan-icon" aria-hidden="true">&#9638;</div>
                <div class="exp-scan-copy">
                  <strong>Scan a receipt</strong>
                  <span class="fine">Qwen3-VL runs on this app server. Your photo is sent to this server for an unsaved preview.</span>
                </div>
                <input id="exp-scan-input" type="file" accept="image/jpeg,image/png,image/webp" hidden>
                <button type="button" class="btn btn-outline" data-action="trigger-scan" ${d.scanBusy || (scanStatus && !scanStatus.available) ? 'disabled' : ''}>${d.scanBusy ? 'Scanning…' : 'Scan receipt'}</button>
                ${d.scanPreviewUrl ? `
                  <figure class="exp-scan-preview ${d.scanBusy ? 'is-scanning' : ''}">
                    <img src="${escapeHtml(d.scanPreviewUrl)}" alt="Receipt you selected, previewed locally">
                    ${d.scanBusy ? '<span class="exp-scan-beam" aria-hidden="true"></span><span class="exp-scan-veil" aria-hidden="true"></span>' : ''}
                    <figcaption class="fine">${d.scanBusy ? 'Reading this receipt on the app server…' : 'Preview only — the selected photo is not saved with the split.'}</figcaption>
                  </figure>` : ''}
              </div>
              <label>Title<input id="exp-split-title" type="text" maxlength="160" value="${escapeHtml(d.title)}" placeholder="Dinner at Luigi's"></label>
              <div class="exp-form-row">
                <label>Category<select id="exp-split-category">${CATEGORIES.map((c) => `<option value="${c}" ${d.category === c ? 'selected' : ''}>${CATEGORY_LABEL[c]}</option>`).join('')}</select></label>
                <label>Group<select id="exp-split-group"><option value="" ${!d.groupId ? 'selected' : ''}>Individual expense</option>${groupOptions}</select></label>
                <label>Total amount (USD)<input id="exp-split-total" type="text" inputmode="decimal" value="${escapeHtml(d.total)}" placeholder="0.00"></label>
              </div>
              <p class="exp-mini-heading">Split with</p>
              <div class="exp-check-grid">${friendChecks || '<p class="fine">Add friends first, or save and split just with yourself.</p>'}</div>
              ${previewLine ? `<p class="fine">${previewLine}</p>` : ''}
            </div>
            <div class="modal-actions-row">
              <button type="button" class="btn btn-outline" data-action="close-modal">Cancel</button>
              <button type="button" class="btn btn-primary" data-action="save-split" ${state.saving ? 'disabled' : ''}>${state.saving ? 'Saving…' : 'Save split'}</button>
            </div>
          </div>
        </div>`;
    }

    function renderSubscriptionModal() {
      const d = state.draft;
      const rows = d.participants.map((p, i) => `
        <div class="exp-form-row">
          <input id="exp-sub-p-name-${i}" type="text" placeholder="Name" value="${escapeHtml(p.name)}">
          <input id="exp-sub-p-wa-${i}" type="text" placeholder="WhatsApp (optional)" value="${escapeHtml(p.whatsapp)}">
          <button type="button" class="btn btn-quiet" data-action="remove-sub-participant" data-index="${i}">Remove</button>
        </div>`).join('');
      return `
        <div class="modal-backdrop" id="exp-sub-modal-backdrop">
          <div class="modal-card">
            <div class="modal-header">
              <div class="split-modal-title">
                <span class="badge badge-gold">RECURRING REMINDER</span>
                <h2>New subscription reminder</h2>
              </div>
              <button type="button" class="modal-close-btn" data-action="close-modal">&times;</button></div>
            <div class="modal-body">
              ${d.formError ? `<p class="exp-error">${escapeHtml(d.formError)}</p>` : ''}
              <label>Name<input id="exp-sub-name" type="text" maxlength="80" value="${escapeHtml(d.name)}" placeholder="Shared streaming plan"></label>
              <div class="exp-form-row">
                <label>Monthly amount (USD)<input id="exp-sub-amount" type="text" inputmode="decimal" value="${escapeHtml(d.monthlyAmount)}" placeholder="0.00"></label>
                <label>Billing day<input id="exp-sub-day" type="number" min="1" max="28" value="${escapeHtml(d.billingDay)}"></label>
              </div>
              <p class="exp-mini-heading">Who shares this</p>
              ${rows}
              <button type="button" class="btn btn-quiet" data-action="add-sub-participant">+ Add person</button>
            </div>
            <div class="modal-actions-row">
              <button type="button" class="btn btn-outline" data-action="close-modal">Cancel</button>
              <button type="button" class="btn btn-primary" data-action="save-subscription" ${state.saving ? 'disabled' : ''}>${state.saving ? 'Saving…' : 'Save'}</button>
            </div>
          </div>
        </div>`;
    }

    function render() {
      const navItems = [['dashboard', 'Groups'], ['activity', 'Activity'], ['friends', 'Friends'], ['subscriptions', 'Subscriptions'], ['analytics', 'Analytics'], ['account', 'Account']];
      const body = {
        dashboard: renderDashboard, activity: renderActivity, friends: renderFriends,
        subscriptions: renderSubscriptions, analytics: renderAnalytics, account: renderAccount,
      }[state.view]();
      container.innerHTML = `
        <div class="exp-wrap">
          <div class="section-header page-intro">
            <div>
              <p class="eyebrow">YOUR OWN LEDGER</p>
              <h1>Split the bill.<br>Settle it your way.</h1>
              <p>Informal notes between you and your people. Nothing here touches PayPal, tickets or inventory.</p>
            </div>
            <span class="badge badge-gold">LOCAL &amp; INFORMAL &mdash; NOT PAYPAL PAYMENT</span>
          </div>
          <div class="exp-toolbar">
            <div class="filter-row">${navItems.map(([key, label]) => `<button type="button" class="filter-pill ${state.view === key ? 'active' : ''}" data-action="nav" data-view="${key}">${label}</button>`).join('')}</div>
            <button type="button" class="btn btn-primary" data-action="new-split">+ New split</button>
          </div>
          ${state.error ? `<p class="exp-error">${escapeHtml(state.error)}</p>` : ''}
          ${state.notice ? `<p class="exp-notice">${escapeHtml(state.notice)}</p>` : ''}
          ${state.busy ? '<p class="fine">Loading…</p>' : body}
        </div>
        ${state.modal === 'split' ? renderSplitModal() : ''}
        ${state.modal === 'subscription' ? renderSubscriptionModal() : ''}`;
    }

    refreshAll();
    return {refresh: refreshAll};
  }

  root.GroupPayExpenses = {mount};
})(window);
