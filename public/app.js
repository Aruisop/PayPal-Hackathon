const $ = (id) => document.getElementById(id);
const steps = ['step-create', 'step-approve', 'step-capture'];
let busy = false;
function message(text, kind = '') { $('status').textContent = text; $('status').className = kind; }
function progress(count) { steps.forEach((id, i) => $(id).classList.toggle('done', i < count)); }
function setBusy(value) { busy = value; $('scenario').disabled = value; $('simulate').disabled = value; }
function reset() { $('receipt').hidden = true; progress(0); }
function receipt(data, simulated = false) {
  $('receipt').hidden = false;
  $('order-id').textContent = data.orderID;
  $('capture-id').textContent = data.captureID;
  $('capture-status').textContent = data.status;
  $('receipt-note').textContent = simulated ? 'Simulated receipt. No PayPal API call was made.' : 'Review this capture in your Business Sandbox account activity.';
}
async function api(path, body) {
  const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) { const error = new Error(data.error || 'REQUEST_FAILED'); error.debugID = data.debugID; throw error; }
  return data;
}
function failure(error) {
  const copy = error.message === 'INSTRUMENT_DECLINED'
    ? 'Payment method declined. Choose another funding method, or switch to the successful scenario and retry.'
    : error.message === 'CREDENTIALS_MISSING' ? 'Add your Sandbox credentials to .env and restart the server.'
    : 'Checkout could not be completed. Please try again. If you already approved a payment, check seller activity before starting another order.';
  message(copy + (error.debugID ? ` Support reference: ${error.debugID}` : ''), 'error');
  setBusy(false);
}
$('simulate').addEventListener('click', async () => {
  if (busy) return;
  setBusy(true); reset();
  const decline = $('scenario').value === 'decline';
  message('Simulation: creating an order…');
  await new Promise(resolve => setTimeout(resolve, 500)); progress(1);
  message('Simulation: buyer approves the payment…');
  await new Promise(resolve => setTimeout(resolve, 500)); progress(2);
  await new Promise(resolve => setTimeout(resolve, 500));
  if (decline) message('Simulated decline: payment method declined. Select the successful scenario to retry.', 'error');
  else { progress(3); message('Simulated payment completed. No PayPal transaction occurred.', 'success'); receipt({orderID: 'SIMULATED-ORDER', captureID: 'SIMULATED-CAPTURE', status: 'COMPLETED'}, true); }
  setBusy(false);
});
async function init() {
  try {
    const response = await fetch('/api/config');
    if (!response.ok) throw new Error('CONFIG_FAILED');
    const config = await response.json();
    $('setup').hidden = config.configured;
    $('mode').textContent = config.configured ? 'Sandbox connected · test money only' : 'Simulation available · PayPal credentials needed';
    if (!config.configured) return;
    const script = document.createElement('script');
    script.src = 'https://www.paypal.com/sdk/js?' + new URLSearchParams({'client-id': config.clientID, currency: config.product.currency, intent: 'capture', components: 'buttons'});
    await new Promise((resolve, reject) => { script.onload = resolve; script.onerror = reject; document.head.append(script); });
    await paypal.Buttons({
      style: {layout: 'vertical', shape: 'rect', label: 'pay'},
      onClick(data, actions) { return busy ? actions.reject() : actions.resolve(); },
      async createOrder() {
        setBusy(true); reset(); message('Creating your Sandbox order…');
        try { const order = await api('/api/orders', {scenario: $('scenario').value}); progress(1); message('Approve the payment using your Personal Sandbox account.'); return order.id; }
        catch (error) { failure(error); throw error; }
      },
      async onApprove(data) {
        progress(2); message('Buyer approved. Capturing the payment…');
        try {
          const result = await api(`/api/orders/${encodeURIComponent(data.orderID)}/capture`, {});
          receipt(result);
          if (result.status === 'COMPLETED') { progress(3); message('Payment completed! Check your Business Sandbox account activity.', 'success'); }
          else message(`Capture status: ${result.status}. Payment is not yet confirmed as completed. Check seller activity.`);
          setBusy(false);
        } catch (error) { failure(error); }
      },
      onCancel() { message('Checkout canceled. No payment was captured by this checkout.'); setBusy(false); },
      onError(error) { if (busy) failure(error); }
    }).render('#paypal-buttons');
  } catch (error) { message('PayPal checkout could not load. You can still try the simulated flow.', 'error'); }
}
init();
