'use strict';
// Actual DOM/controllers + HTTP + local model; jsdom does not render a browser.
// Start serve_ai_ui_fixture.py first. Supply a pinned jsdom installation as argv2.
const assert = require('node:assert/strict');
const path = require('node:path');
const {JSDOM, CookieJar, ResourceLoader, VirtualConsole} = require(process.argv[2] ? path.resolve(process.argv[2]) : 'jsdom');
const origin = 'http://127.0.0.1:8021';
const doms = [], errors = [], requests = [];
let failNextComparison = false;
class LocalResources extends ResourceLoader {
  fetch(url, options) { return new URL(url).origin === origin ? super.fetch(url, options) : null; }
}
async function waitFor(test, label) {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    if (test()) return;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error(`Timed out: ${label}`);
}
async function profile() {
  const jar = new CookieJar(), console = new VirtualConsole();
  console.on('jsdomError', (error) => errors.push(error.message));
  const dom = await JSDOM.fromURL(origin, {cookieJar: jar, runScripts: 'dangerously',
    resources: new LocalResources(), virtualConsole: console, pretendToBeVisual: true,
    beforeParse(window) {
      window.HTMLElement.prototype.scrollIntoView = function () {};
      window.alert = (message) => errors.push(message);
      window.confirm = () => true;
      window.fetch = async (url, options = {}) => {
        const target = new URL(url, origin); assert.equal(target.origin, origin);
        requests.push({path: target.pathname, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : null});
        if (failNextComparison && target.pathname.endsWith('/recommendations')) {
          failNextComparison = false;
          return new Response(JSON.stringify({error: 'RECOMMENDATION_STALE'}), {status: 409, headers: {'Content-Type': 'application/json'}});
        }
        const headers = new Headers(options.headers);
        const cookie = jar.getCookieStringSync(origin); if (cookie) headers.set('Cookie', cookie);
        if (options.method === 'POST') headers.set('Origin', origin);
        const reply = await fetch(target, {...options, headers});
        const setCookie = reply.headers.get('set-cookie'); if (setCookie) jar.setCookieSync(setCookie, origin);
        return reply;
      };
    }});
  doms.push(dom);
  await waitFor(() => dom.window.GroupPayRoom && dom.window.eval('typeof config !== "undefined" && Boolean(config?.participantID)') &&
    dom.window.document.getElementById('my-groups-container').textContent.includes('No groups yet'), 'complete application bootstrap');
  return dom.window;
}
const element = (window, id) => window.document.getElementById(id);
function submit(window, id) { element(window, id).dispatchEvent(new window.Event('submit', {bubbles: true, cancelable: true})); }
function change(window, id, value, event = 'input') {
  element(window, id).value = value;
  element(window, id).dispatchEvent(new window.Event(event, {bubbles: true}));
}
function action(window, label) {
  const button = [...element(window, 'room-ai-actions').querySelectorAll('button')].find((item) => item.textContent.includes(label));
  assert.ok(button, `Missing action: ${label}`); button.click();
}
async function confirmWithoutTastes(window) {
  element(window, 'room-show-preferences').click();
  assert.equal(element(window, 'room-preferences-stage').hidden, false);
  element(window, 'chat-input-text').value = 'Any day and time, budget under $100';
  submit(window, 'chat-input-form');
  await waitFor(() => !element(window, 'room-preference-review').hidden && !element(window, 'room-preference-review').querySelector('button').disabled, 'private preference review');
  assert.equal(element(window, 'pref-soft').value, '');
  submit(window, 'room-preference-review');
  await waitFor(() => element(window, 'pref-review-status').textContent.includes('CONFIRMED') && !element(window, 'room-ai-recommend').disabled, 'preference confirmation');
  assert.equal(element(window, 'room-comparison-stage').hidden, false, 'Explicit confirmation advances to comparison');
  assert.equal(element(window, 'room-preferences-stage').hidden, true);
}

(async () => {
  const owner = await profile(), friend = await profile();
  const group = await owner.api('/api/groups', {name: 'Synthetic DOM integration group'});
  await friend.api('/api/groups/join', {inviteToken: new URL(group.inviteURL).searchParams.get('invite')});
  const catalog = await owner.api('/api/catalog/offers');
  const starting = catalog.offers.find((offer) => offer.domain === 'movie');
  assert.deepEqual(starting.availability.groupSizes, [2, 3, 4]);
  await owner.selectGroup(group.id, starting); await friend.selectGroup(group.id);
  assert.match(element(owner, 'room-starting-point').textContent, new RegExp(starting.title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  assert.equal(element(owner, 'room-preferences-stage').hidden, false);
  assert.equal(element(owner, 'room-show-comparison').disabled, true, 'Comparison stage waits for explicit own confirmation');
  await confirmWithoutTastes(owner); await confirmWithoutTastes(friend);
  element(owner, 'room-ai-recommend').click();
  assert.match(element(owner, 'room-ai-recommend').textContent, /Comparing your group/);
  assert.equal(element(owner, 'room-ai-recommend').getAttribute('aria-busy'), 'true');
  await waitFor(() => element(owner, 'room-ai-actions').querySelector('button') && element(owner, 'room-ai-recommend').disabled, 'missing-tastes action');
  assert.match(element(owner, 'room-ai-ranking-note').textContent, /did not run/);
  const confirmations = () => requests.filter((request) => request.path.endsWith('/preferences/confirm')).length;
  const before = confirmations();
  element(owner, 'room-ai-actions').querySelector('button').click();
  assert.equal(owner.document.activeElement.id, 'pref-soft', 'Action focuses the actual editable DOM field');
  assert.match(element(owner, 'room-preference-review').querySelector('button').textContent, /confirm.*compare/i);
  element(owner, 'pref-soft').value = 'science fiction';
  element(owner, 'pref-soft').dispatchEvent(new owner.Event('input', {bubbles: true}));
  assert.equal(confirmations(), before, 'Editing or clicking compare never confirms on the user behalf');
  element(owner, 'room-ai-recommend').click();
  assert.equal(confirmations(), before);
  submit(owner, 'room-preference-review');
  await waitFor(() => element(owner, 'room-ai-ranking-note').textContent.includes('Local model:') && !element(owner, 'room-ai-recommend').disabled, 'automatic comparison after explicit confirmation');
  assert.match(element(owner, 'room-ai-ranking-note').textContent, /bge-small-en-v1.5/);
  assert.match(element(owner, 'room-ai-ranking-note').textContent, /1\/2 members/);
  assert.match(element(owner, 'room-plan-results').textContent, /AI compared 3 verified experiences/);
  assert.equal(element(owner, 'brief-choices').textContent, '3');
  assert.equal(element(owner, 'brief-method').textContent, 'Local AI comparison');
  assert.match(element(owner, 'room-plan-results').textContent, /YOUR STARTING POINT/);
  const peer = await friend.api(`/api/groups/${group.id}/preferences`);
  assert.deepEqual(peer.confirmedConstraints.soft_preferences, [], 'Peer preferences remain unchanged');
  element(owner, 'room-ai-objective').value = 'average';
  element(owner, 'room-ai-objective').dispatchEvent(new owner.Event('change', {bubbles: true}));
  assert.equal(element(owner, 'room-ai-ranking-note').textContent, '');
  failNextComparison = true; element(owner, 'room-ai-recommend').click();
  await waitFor(() => element(owner, 'room-ai-ranking-note').textContent.includes('could not finish') && !element(owner, 'room-ai-recommend').disabled, 'visible request failure');
  assert.equal(element(owner, 'room-plan-results').children.length, 0, 'A failed comparison cannot leave stale cards selectable');
  assert.match(element(owner, 'room-ai-actions').textContent, /Retry/);
  element(owner, 'room-ai-actions').querySelector('button').click();
  await waitFor(() => element(owner, 'room-ai-ranking-note').textContent.includes('Local model:') && !element(owner, 'room-ai-recommend').disabled, 'successful retry');
  assert.equal(requests.filter((request) => request.path.endsWith('/recommendations')).at(-1).body.objective, 'average');

  element(owner, 'room-show-preferences').click();
  change(owner, 'pref-budget', '20.00'); submit(owner, 'room-preference-review');
  await waitFor(() => !element(owner, 'room-ai-recommend').disabled && element(owner, 'pref-review-status').textContent.includes('CONFIRMED'), 'lower own budget confirmed');
  change(owner, 'room-domain', 'excursion', 'change'); element(owner, 'room-ai-recommend').click();
  await waitFor(() => element(owner, 'room-plan-results').querySelectorAll('.room-blocked').length === 2 && element(owner, 'room-ai-recommend').disabled, 'no-match diagnostic cards');
  assert.match(element(owner, 'room-ai-ranking-note').textContent, /No eligible plan/);
  assert.doesNotMatch(element(owner, 'room-ai-ranking-note').textContent, /error|did not run|\(no matches\)/i);
  assert.match(element(owner, 'room-plan-results').textContent, /Your exact share: 50.00 USD/);
  assert.match(element(owner, 'room-plan-results').textContent, /Your exact share: 60.00 USD/);
  assert.match(element(owner, 'room-plan-results').textContent, /Your confirmed budget is below this share/);
  assert.equal(element(owner, 'room-plan-results').querySelectorAll('button').length, 0, 'Blocked plans cannot be selected');
  action(owner, 'Review my budget');
  assert.equal(element(owner, 'room-preferences-stage').hidden, false);
  assert.equal(owner.document.activeElement.id, 'pref-budget');
  assert.equal(element(owner, 'pref-advanced').open, true);
  element(owner, 'room-show-comparison').click();
  action(owner, 'Find changes I can make');
  await waitFor(() => element(owner, 'room-rescue-results').querySelectorAll('.rescue-option').length === 2, 'verified own-only proposals');
  const beforePreview = confirmations();
  element(owner, 'room-rescue-results').querySelectorAll('.rescue-option')[1].querySelector('button').click();
  assert.equal(element(owner, 'pref-budget').value, '60.00');
  assert.equal(confirmations(), beforePreview, 'Counterfactual preview never confirms preferences');
  assert.equal((await owner.api(`/api/groups/${group.id}/preferences`)).confirmedConstraints.budget_cents, 2000);
  assert.match(element(owner, 'room-preference-review').querySelector('button').textContent, /confirm.*compare/i);
  submit(owner, 'room-preference-review');
  await waitFor(() => element(owner, 'room-ai-ranking-note').textContent.includes('Local model:') && !element(owner, 'room-ai-recommend').disabled, 'AI resumes after explicit tradeoff confirmation');
  assert.match(element(owner, 'room-plan-results').textContent, /AI compared 2 verified experiences/);
  assert.deepEqual((await friend.api(`/api/groups/${group.id}/preferences`)).confirmedConstraints, peer.confirmedConstraints, 'Own tradeoff leaves all peer constraints unchanged');

  element(friend, 'room-show-preferences').click();
  change(friend, 'pref-budget', '20.00'); submit(friend, 'room-preference-review');
  await waitFor(() => !element(friend, 'room-ai-recommend').disabled && element(friend, 'pref-review-status').textContent.includes('CONFIRMED'), 'peer chooses own lower budget');
  element(owner, 'room-refresh').click();
  await waitFor(() => element(owner, 'room-ai-ranking-note').textContent.includes('Group preferences changed') && !element(owner, 'room-ai-recommend').disabled, 'peer edit invalidates the old comparison');
  assert.equal(element(owner, 'room-plan-results').children.length, 0);
  assert.equal(element(owner, 'brief-choices').textContent, 'Not checked');
  element(owner, 'room-ai-recommend').click();
  await waitFor(() => element(owner, 'room-plan-results').querySelectorAll('.room-blocked').length === 2 && element(owner, 'room-ai-recommend').disabled, 'peer-only block visible');
  assert.doesNotMatch(element(owner, 'room-plan-results').textContent, /Your confirmed budget is below/);
  assert.match(element(owner, 'room-plan-results').textContent, /Another member/);
  action(owner, 'Find changes I can make');
  await waitFor(() => element(owner, 'room-rescue-results').textContent.includes('Changing only your preferences cannot unlock'), 'own edits cannot bypass peer limits');
  assert.equal(element(owner, 'room-rescue-results').querySelectorAll('button').length, 0);
  action(owner, 'View 3 cinema nights');
  await waitFor(() => element(owner, 'room-ai-ranking-note').textContent.includes('Local model:') && !element(owner, 'room-ai-recommend').disabled, 'explicit category switch compares eligible alternatives');
  assert.equal(element(owner, 'room-domain').value, 'movie');
  assert.match(element(owner, 'room-plan-results').textContent, /AI compared 3 verified experiences/);

  change(owner, 'room-domain', 'excursion', 'change'); element(owner, 'room-ai-recommend').click();
  await waitFor(() => element(owner, 'room-plan-results').querySelectorAll('.room-blocked').length === 2 && element(owner, 'room-ai-recommend').disabled, 'diagnostics before roster change');
  const third = await profile();
  await third.api('/api/groups/join', {inviteToken: new URL(group.inviteURL).searchParams.get('invite')});
  element(owner, 'room-refresh').click();
  await waitFor(() => element(owner, 'room-ai-ranking-note').textContent.includes('Group size changed') && !element(owner, 'room-ai-recommend').disabled, 'roster-change invalidation');
  assert.equal(element(owner, 'room-plan-results').children.length, 0, 'Stale shares and blockers disappear after roster change');
  assert.equal(element(owner, 'room-rescue-results').children.length, 0);
  assert.deepEqual(errors, []);
  console.log('Actual DOM + live temporary API + real BGE passed: staged preferences/comparison, discovery intent, truthful decision brief, taste onboarding, retries, blocked shares, explicit tradeoffs, category switch, peer-edit and roster invalidation. No rendered-browser or payment claim.');
})().catch((error) => { console.error(error); process.exitCode = 1; }).finally(() => { for (const dom of doms) dom.window.close(); });
