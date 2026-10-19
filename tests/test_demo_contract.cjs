'use strict';
// Run: node tests/test_demo_contract.cjs. No packages, server or credentials.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const demo = require('../public/demo.js');
const source = fs.readFileSync(path.join(__dirname, '../public/demo.js'), 'utf8');
let passed = 0;
function test(name, check) { check(); passed++; console.log(`ok ${passed} - ${name}`); }
function prepared(scenario = 'movie') {
  let state = demo.createState([], scenario);
  for (let index = 0; index < 3; index++) state = demo.reduce(state, {type: 'PREFERENCE', index, budget: 5000, notes: `${index}'s fictional notes`});
  state = demo.reduce(state, {type: 'FREEZE'});
  return state;
}
function authorized(scenario) {
  let state = prepared(scenario);
  for (let index = 0; index < 3; index++) state = demo.reduce(state, {type: 'AUTHORIZE', index});
  return demo.reduce(state, {type: 'FINALIZE'});
}
function completed() {
  let state = authorized('movie');
  for (let i = 0; i < 3; i++) state = demo.reduce(state, {type: 'CAPTURE'});
  return state;
}

test('exact safe integer shares and decimal input', () => {
  assert.deepEqual(demo.split(10000), [3334, 3333, 3333]);
  assert.equal(demo.split(10000).reduce((a, b) => a + b), 10000);
  assert.equal(demo.cents('33.34'), 3334);
  assert.equal(demo.cents('0'), 0);
  for (const bad of ['-1', '1.234', '1e2', '', 'Infinity']) assert.throws(() => demo.cents(bad));
  assert.throws(() => demo.split(Number.MAX_SAFE_INTEGER + 1));
  assert.throws(() => demo.split(10, 0));
});
test('three independently confirmed budgets gate the quote', () => {
  let state = demo.createState([]);
  assert.throws(() => demo.reduce(state, {type: 'FREEZE'}), /confirm preferences/);
  for (let index = 0; index < 3; index++) state = demo.reduce(state, {type: 'PREFERENCE', index, budget: index === 2 ? 1000 : 5000});
  assert.match(demo.quote(state).conflicts.join(' '), /Charlie: \$6.00 over/);
  assert.throws(() => demo.reduce(state, {type: 'FREEZE'}));
});
test('copied catalog and reducer inputs stay untouched', () => {
  const offers = [{id: 'real-offer', domain: 'movie', title: '<img src=x>', priceMinor: 1800, currency: 'USD', resources: [1, 2, 3].map((i) => ({id: `real-${i}`, row: 'A', col: i, label: `A${i}`, state: 'BOOKED'}))}];
  const snapshot = JSON.stringify(offers);
  const state = demo.createState(offers); const before = JSON.stringify(state);
  const changed = demo.reduce(state, {type: 'PREFERENCE', index: 0, budget: 3000});
  assert.equal(JSON.stringify(offers), snapshot); assert.equal(JSON.stringify(state), before);
  assert.equal(changed.members[0].confirmed, true);
  assert.equal(state.members[0].confirmed, false);
  assert.match(state.selected, /^SIM-/);
  assert.equal(state.offers[0].total, 5400);
  assert.match(state.offers[0].source, /real availability is not reserved/);
});
test('nonadjacent cinema seats cannot freeze', () => {
  let state = demo.createState([]); const offer = state.offers.find((o) => o.id === state.selected);
  for (let index = 0; index < 3; index++) state = demo.reduce(state, {type: 'PREFERENCE', index, budget: 5000});
  state = demo.reduce(state, {type: 'RESOURCE', id: offer.resources[1].id});
  state = demo.reduce(state, {type: 'RESOURCE', id: offer.resources[5].id});
  assert.match(demo.quote(state).conflicts.join(' '), /adjacent/);
  assert.throws(() => demo.reduce(state, {type: 'FREEZE'}));
});
test('individual authorization gates finalization; authorization creates no ticket', () => {
  let state = prepared();
  assert.throws(() => demo.reduce(state, {type: 'FINALIZE'}), /Each fictional participant/);
  state = demo.reduce(state, {type: 'AUTHORIZE', index: 0});
  assert.equal(state.ledger.length, 0);
  assert.throws(() => demo.reduce(state, {type: 'AUTHORIZE', index: 0}), /already authorized/);
  assert.throws(() => demo.reduce(state, {type: 'PREFERENCE', index: 0, budget: 0}));
  assert.throws(() => demo.reduce(state, {type: 'SELECT', id: state.offers[1].id}));
});
test('sequential exact captures gate private passes', () => {
  let state = authorized('excursion');
  assert.deepEqual(state.shares, [3334, 3333, 3333]);
  for (let i = 0; i < 2; i++) { state = demo.reduce(state, {type: 'CAPTURE'}); assert.equal(state.ledger.length, 0); assert.equal(state.inventory, 'HELD'); }
  state = demo.reduce(state, {type: 'CAPTURE'});
  assert.equal(state.phase, 'CONFIRMED'); assert.equal(state.inventory, 'BOOKED'); assert.equal(state.ledger.length, 3);
  const alice = demo.participantView(state, 0);
  assert.equal(alice.ticket.holder, 'Alice'); assert.match(alice.ticket.code, /^SIM-/);
  assert.equal(JSON.stringify(alice).includes('Bob'), false);
  alice.ticket.used = true;
  assert.equal(state.ledger[0].used, false);
  assert.throws(() => demo.participantView(state, -1));
});
test('chaos failure retains seats and pending compensation until every outcome completes', () => {
  let state = authorized('chaos');
  for (let i = 0; i < 3; i++) state = demo.reduce(state, {type: 'CAPTURE'});
  assert.equal(state.phase, 'RECOVERY'); assert.equal(state.inventory, 'HELD'); assert.equal(state.ledger.length, 0);
  assert.deepEqual(state.members.map((m) => m.payment), ['REFUND_PENDING', 'REFUND_PENDING', 'VOID_PENDING']);
  assert.equal(state.timeline.some((line) => /refund completed/.test(line)), false);
  for (let i = 0; i < 2; i++) { state = demo.reduce(state, {type: 'RECOVER'}); assert.equal(state.inventory, 'HELD'); }
  state = demo.reduce(state, {type: 'RECOVER'});
  assert.equal(state.phase, 'CANCELLED'); assert.equal(state.inventory, 'FREE');
  assert.deepEqual(state.members.map((m) => m.payment), ['REFUNDED', 'REFUNDED', 'VOIDED']);
  assert.equal(state.ledger.length, 0); assert.throws(() => demo.reduce(state, {type: 'RECOVER'}));
});
test('readiness uses entered hypothetical amounts and finds an actual cheaper copied offer', () => {
  let state = demo.createState([], 'excursion');
  state = demo.reduce(state, {type: 'AVAILABLE', index: 0, amount: 2000});
  const check = demo.readiness(state, 0);
  assert.equal(check.gap, 1334); assert.equal(check.required, 3334);
  assert.equal(check.alternatives.length, 1); assert.match(check.alternatives[0], /cinema/);
  assert.equal(state.members[0].payment, 'NOT_STARTED'); assert.equal(state.inventory, 'FREE');
});
test('scanner checks a confirmed ledger and rejects invalid and duplicate admission', () => {
  let state = demo.reduce(prepared(), {type: 'SCAN', code: 'SIM-TICKET-1-1'});
  assert.match(state.scan, /Rejected/);
  state = completed();
  state = demo.reduce(state, {type: 'SCAN', code: 'invented'}); assert.match(state.scan, /Rejected/);
  const code = state.ledger[0].code;
  state = demo.reduce(state, {type: 'SCAN', code}); assert.match(state.scan, /Admitted Alice/);
  assert.equal(state.ledger[0].used, true);
  state = demo.reduce(state, {type: 'SCAN', code}); assert.match(state.scan, /already admitted/);
  assert.equal(state.ledger[1].used, false);
  state = demo.reduce(state, {type: 'RESET'});
  state = demo.reduce(state, {type: 'SCAN', code}); assert.match(state.scan, /Rejected/);
  assert.equal(state.run, 2); assert.equal(state.ledger.length, 0);
});
test('persona and explicit three-way view change only local presentation', () => {
  let state = prepared(); const memberSnapshot = JSON.stringify(state.members);
  state = demo.reduce(state, {type: 'PERSONA', index: 2});
  assert.equal(state.active, 2); assert.equal(state.splitView, false);
  state = demo.reduce(state, {type: 'SPLIT_VIEW'}); assert.equal(state.splitView, true);
  state = demo.reduce(state, {type: 'PERSONA', index: 1}); assert.equal(state.splitView, false);
  assert.equal(JSON.stringify(state.members), memberSnapshot);
  assert.throws(() => demo.reduce(state, {type: 'PERSONA', index: 8}));
});
test('browser source excludes network, persistence, unsafe HTML and fake QR APIs', () => {
  assert.doesNotMatch(source, /\b(fetch|XMLHttpRequest|WebSocket|localStorage|sessionStorage|indexedDB)\b|document\.cookie|\.innerHTML|drawQRCode/);
});

// Minimal DOM exercises mount/render independently of server and browser APIs.
class Element {
  constructor(tag, document) { this.tagName = tag; this.ownerDocument = document; this.children = []; this.attributes = {}; this.handlers = {}; this.textContent = ''; }
  append(...nodes) { this.children.push(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(key, value) { this.attributes[key] = value; }
  getAttribute(key) { return this.attributes[key] || null; }
  addEventListener(name, handler) { this.handlers[name] = handler; }
  contains(node) { return this === node || this.children.some((child) => child.contains?.(node)); }
  querySelectorAll() { return this.children.flatMap((child) => [child, ...(child.querySelectorAll?.() || [])]); }
  focus() { this.ownerDocument.activeElement = this; }
}
test('browser mount is isolated, text-rendered and resettable without external capabilities', () => {
  const browser = {};
  vm.runInNewContext(source, {window: browser});
  const document = {activeElement: null, createElement(tag) { return new Element(tag, this); }};
  const one = new Element('main', document); const two = new Element('main', document);
  const first = browser.GroupPayDemo.mount(one, {offers: []});
  const second = browser.GroupPayDemo.mount(two, {offers: []});
  assert.equal(one.children.length, 1); assert.equal(two.children.length, 1);
  const all = one.querySelectorAll();
  const reset = all.find((node) => node.textContent === 'Reset local demo'); reset.handlers.click();
  assert.equal(first.getState().run, 2); assert.equal(second.getState().run, 1);
  assert.ok(all.some((node) => /No PayPal, Gemini, bank query/.test(node.textContent)));
  first.destroy(); assert.equal(one.children.length, 0); assert.equal(two.children.length, 1);
  function click(text) {
    const control = two.querySelectorAll().find((node) => node.tagName === 'button' && node.textContent === text);
    assert.ok(control, `Missing demo control: ${text}`); assert.notEqual(control.disabled, true); control.handlers.click();
  }
  click('Chaos Lab · third capture fails');
  for (const name of ['Alice', 'Bob', 'Charlie']) {
    click(name);
    const form = two.querySelectorAll().find((node) => node.tagName === 'form' && node.querySelectorAll().some((child) => child.textContent === 'Confirm my preferences'));
    assert.ok(form); form.handlers.submit({preventDefault() {}});
  }
  click('Freeze local quote & hold places');
  for (const name of ['Alice', 'Bob', 'Charlie']) { click(name); click(`Simulate ${name}'s approval`); }
  click('Start local finalization');
  for (const [index, name] of ['Alice', 'Bob', 'Charlie'].entries()) click(`Simulate capture ${index + 1} of 3 · ${name}`);
  assert.equal(second.getState().phase, 'RECOVERY');
  for (let i = 0; i < 3; i++) click('Complete next simulated recovery item');
  assert.equal(second.getState().phase, 'CANCELLED');
  assert.equal(second.getState().ledger.length, 0);
});
console.log(`${passed} isolated demo contract checks passed.`);
