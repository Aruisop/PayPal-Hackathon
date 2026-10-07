const $ = (id) => document.getElementById(id);
let config, selectedWorkshop, selectedBooking, paypalButtons;
let busy = false, sdkReady = false, renderVersion = 0;
const bookings = new Map();
const unresolved = new Set(['CREATING', 'CAPTURING', 'PENDING', 'UNKNOWN']);
function message(text, kind = '') { $('status').textContent = text; $('status').className = kind; }
function setBusy(value) {
  busy = value;
  document.querySelectorAll('[data-workshop]').forEach((button) => { button.disabled = value; });
  $('recheck').disabled = value;
  $('complete-payment').disabled = value;
}
async function api(path, body) {
  const options = {credentials: 'same-origin', cache: 'no-store'};
  if (body !== undefined) {
    options.method = 'POST';
    options.headers = {'Content-Type': 'application/json', 'X-CSRF-Token': config.csrfToken};
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); }
  catch { throw new Error('Server response could not be read. Recheck an existing payment before retrying.'); }
  if (!response.ok) throw new Error(data.message || data.error || 'The request could not be completed.');
  return data;
}
function price(workshop) {
  return new Intl.NumberFormat('en-US', {style: 'currency', currency: workshop.currency}).format(workshop.value);
}
function schedule(workshop) {
  const format = new Intl.DateTimeFormat(undefined, {dateStyle: 'medium', timeStyle: 'short'});
  return `${format.format(new Date(workshop.startsAt))} – ${format.format(new Date(workshop.endsAt))}`;
}
function state(booking) { return String(booking?.attemptState || 'NOT_STARTED').toUpperCase(); }
function saveBooking(booking) {
  bookings.set(booking.id, booking);
  if (selectedWorkshop?.id === booking.workshopID) selectedBooking = booking;
  renderBookings();
}
function defaultStatus(booking) {
  if (!booking) return 'Pay with your Personal Sandbox account. Your booking is saved before checkout opens.';
  if (booking.lessonURL) return 'Payment completed. Your own sample lesson is now available.';
  switch (state(booking)) {
    case 'PENDING': return 'PayPal is processing the capture. Access remains locked; recheck the payment.';
    case 'UNKNOWN': return 'Payment outcome is unresolved. Recheck with PayPal before another payment attempt.';
    case 'CAPTURING': return 'Capture is in progress. Access remains locked until completion is confirmed.';
    case 'CREATING': return 'Your saved payment attempt is being resolved. Recheck before continuing.';
    case 'APPROVED': return 'Buyer approval received. Completed payment is not confirmed; access remains locked.';
    case 'DENIED': case 'FAILED': return 'This payment attempt did not complete. Access remains locked.';
    case 'CANCELLED': return 'Checkout was cancelled. Access remains locked.';
    case 'AWAITING_APPROVAL': return 'Your order is saved. Continue checkout to approve and complete payment.';
    default: return 'Payment is not confirmed. Access remains locked.';
  }
}
function renderStatus() {
  const booking = selectedBooking;
  $('receipt').hidden = !booking;
  $('lesson').hidden = !booking?.lessonURL;
  $('lesson').removeAttribute('href');
  if (booking?.lessonURL) $('lesson').href = booking.lessonURL;
  $('recheck').hidden = !booking || !!booking.lessonURL;
  $('complete-payment').hidden = !booking || booking.attemptState !== 'APPROVED' || !booking.orderID || !!booking.lessonURL;
  if (booking) {
    for (const [id, value] of Object.entries({
      'booking-id': booking.id, 'booking-state': booking.bookingState,
      'attempt-state': booking.attemptState, 'order-id': booking.orderID, 'capture-id': booking.captureID,
    })) $(id).textContent = value || 'Not recorded';
  }
  message(booking?.message || defaultStatus(booking), booking?.lessonURL ? 'success' : unresolved.has(state(booking)) ? 'warning' : '');
}
function renderBookings() {
  const container = $('bookings');
  container.replaceChildren();
  if (!bookings.size) {
    const empty = document.createElement('p'); empty.className = 'fine';
    empty.textContent = 'No bookings in this browser profile yet.'; container.append(empty);
  }
  for (const booking of bookings.values()) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'booking-row'; button.dataset.workshop = booking.workshopID;
    button.disabled = busy;
    button.textContent = `${booking.workshopTitle || booking.workshopID} · ${booking.bookingState} / ${booking.attemptState || 'NOT_STARTED'}`;
    button.addEventListener('click', () => selectWorkshop(booking.workshopID)); container.append(button);
  }
}
async function refreshBooking(id) {
  const booking = await api(`/api/bookings/${encodeURIComponent(id)}`);
  saveBooking(booking);
  if (selectedBooking?.id === id) renderStatus();
  return booking;
}
async function recover(error, bookingID) {
  // A browser error cannot prove a capture failed. Keep the saved attempt visible.
  if (bookingID) {
    try { await refreshBooking(bookingID); } catch { /* Retain last known state when offline. */ }
  }
  message(`${error.message || 'Checkout was interrupted.'} Recheck your saved payment before another attempt.`, 'error');
}
async function renderCheckout() {
  const version = ++renderVersion;
  if (paypalButtons) {
    try { await paypalButtons.close(); } catch { /* The SDK may already have closed its frame. */ }
    paypalButtons = undefined;
  }
  if (version !== renderVersion) return;
  $('paypal-buttons').replaceChildren();
  if (!sdkReady || !selectedWorkshop || (selectedBooking &&
      (!selectedBooking.canPay || selectedBooking.attemptState === 'APPROVED'))) return;
  const workshopID = selectedWorkshop.id;
  let bookingID = selectedBooking?.id;
  const buttons = window.paypal.Buttons({
    style: {layout: 'vertical', shape: 'rect', label: 'pay'},
    onClick(data, actions) { return busy ? actions.reject() : actions.resolve(); },
    async createOrder() {
      setBusy(true); message('Saving your booking and preparing PayPal checkout…');
      try {
        const booking = await api('/api/orders', {workshopID});
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
      // Remove a stale button when the saved attempt now requires reconciliation.
      if (selectedBooking && !selectedBooking.canPay) await renderCheckout();
    },
  });
  paypalButtons = buttons;
  try { await buttons.render('#paypal-buttons'); }
  catch { if (version === renderVersion) message('PayPal checkout could not load. Refresh or recheck an existing payment.', 'error'); }
}
async function selectWorkshop(id) {
  if (busy) return;
  selectedWorkshop = config.workshops.find((workshop) => workshop.id === id);
  if (!selectedWorkshop) return;
  selectedBooking = [...bookings.values()].find((booking) => booking.workshopID === id);
  $('checkout-heading').textContent = selectedWorkshop.title;
  $('price').textContent = price(selectedWorkshop); $('schedule').textContent = schedule(selectedWorkshop);
  document.querySelectorAll('.workshop-card').forEach((card) => {
    const active = card.dataset.workshop === id;
    card.classList.toggle('selected', active); card.setAttribute('aria-pressed', String(active));
  });
  renderStatus(); await renderCheckout();
}
$('recheck').addEventListener('click', async () => {
  if (busy || !selectedBooking) return;
  const bookingID = selectedBooking.id;
  setBusy(true); message('Checking the saved payment with PayPal…');
  try { saveBooking(await api(`/api/bookings/${encodeURIComponent(bookingID)}/reconcile`, {})); renderStatus(); }
  catch (error) { await recover(error, bookingID); }
  finally { setBusy(false); await renderCheckout(); }
});
$('complete-payment').addEventListener('click', async () => {
  const booking = selectedBooking;
  if (busy || !booking || booking.attemptState !== 'APPROVED' || !booking.orderID) return;
  setBusy(true); message('Checking the approved order and completing your payment…');
  try {
    const completed = await api(`/api/orders/${encodeURIComponent(booking.orderID)}/capture`, {});
    saveBooking(completed); renderStatus();
  } catch (error) { await recover(error, booking.id); }
  finally { setBusy(false); await renderCheckout(); }
});
async function init() {
  try {
    config = await api('/api/config'); config.bookings.forEach(saveBooking); renderBookings();
    // An SDK onApprove callback may be lost when the buyer returns or reloads.
    // Recheck only saved, uncompleted orders that still await buyer approval.
    const interruptedApprovals = config.bookings.filter((booking) =>
      booking.attemptState === 'AWAITING_APPROVAL' && booking.orderID);
    await Promise.all(interruptedApprovals.map(async (booking) => {
      try { saveBooking(await api(`/api/bookings/${encodeURIComponent(booking.id)}/reconcile`, {})); }
      catch { /* Keep the saved order visible; manual recheck remains available. */ }
    }));
    renderBookings();
    $('setup').hidden = config.configured;
    $('mode').textContent = config.configured ? 'Sandbox connected · test money only' : 'Sandbox checkout not configured';
    $('timezone').textContent = `Schedules shown in your browser timezone: ${Intl.DateTimeFormat().resolvedOptions().timeZone}.`;
    for (const workshop of config.workshops) {
      const card = document.createElement('button');
      card.type = 'button'; card.className = 'workshop-card'; card.dataset.workshop = workshop.id;
      card.setAttribute('aria-pressed', 'false');
      const title = document.createElement('h2'); title.textContent = workshop.title;
      const description = document.createElement('p'); description.textContent = workshop.description;
      const time = document.createElement('p'); time.className = 'fine'; time.textContent = schedule(workshop);
      const amount = document.createElement('strong'); amount.textContent = `${price(workshop)} ${workshop.currency}`;
      card.append(title, description, time, amount);
      card.addEventListener('click', () => selectWorkshop(workshop.id)); $('workshops').append(card);
    }
    await selectWorkshop(config.workshops[0]?.id);
    if (!config.configured) return;
    const script = document.createElement('script');
    script.src = 'https://www.paypal.com/sdk/js?' + new URLSearchParams({
      'client-id': config.clientID, currency: 'USD', intent: 'capture', components: 'buttons',
    });
    await new Promise((resolve, reject) => {
      script.onload = resolve; script.onerror = () => reject(new Error('PayPal SDK could not load. Check your connection and refresh.'));
      document.head.append(script);
    });
    sdkReady = true; await renderCheckout();
  } catch (error) { message(error.message || 'Workshop checkout could not load. Refresh to try again.', 'error'); }
}
// Read-only refreshes never repeatedly initiate or capture payments.
setInterval(async () => {
  if (busy || !selectedBooking || !unresolved.has(state(selectedBooking)) || document.hidden) return;
  try {
    const wasPayable = selectedBooking.canPay; await refreshBooking(selectedBooking.id);
    if (wasPayable !== selectedBooking.canPay || selectedBooking.lessonURL) await renderCheckout();
  } catch { /* Manual recheck remains available; retain last known state. */ }
}, 10000);
init();
