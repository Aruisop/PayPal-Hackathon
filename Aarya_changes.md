# Aarya changes: guided UI improvements and integration review

Date: 18 October 2026. Base: Panchadip-128's `slice/3-collaborative-booking-and-equal-payments`, commit `41ec3d7`. Status: implementation review candidate; acceptance and live-payment evidence remain pending.

## Publication scope: UI-first review snapshot

Target: [Aruisop/PayPal-Hackathon, dev/aarya](https://github.com/Aruisop/PayPal-Hackathon/tree/dev/aarya). The user explicitly scoped this delivery primarily as UI improvement and authorized publishing the current accumulated work. The remote branch was at `8af8e73` (earlier group coordination); Panchadip's original Slice 3 base `41ec3d7` descends from it. Publishing from that base preserves his existing commit history and authorship. The application is published at the target repository root, without embedding the workspace's nested `.git` repository or copying the archived parent application.

The current delta includes the guided UI, prior backend integration repairs, migration revisions 4/5, shared chat, QR encoding, isolated rehearsal, rules-based Plan Rescue, tests and documentation. It is not honestly described as a frontend-only patch. The new commit leads with UI improvement and states the additional scope in its body.

AI status: model-loading/semantic-ranking code is integrated but actual inference is unverified; automated embeddings are mocked. Plan Rescue itself is deterministic, not generative AI. Without a Gemini key the private assistant uses a rules parser. This publication is not a completed or validated AI product. Visual/browser checks and genuine multi-buyer Sandbox evidence remain pending as described below.

Local credentials, databases, archives and runtime state are excluded. No merge, deployment, production-money readiness or external acceptance is implied.

## Latest pass: guided redesign and on-device AI

The user explicitly requested a better UI and real AI novelty after the original-style integration. This pass supersedes the prior requirement to keep the original presentation; it preserves the collaborative booking capabilities and corrected financial protocol. The source-only checkpoint is ignored under `../.local-archive/before-guided-design-*`. No financial data or credentials were copied into it.

- Rebuilt `public/index.html` and `public/style.css` as a light/navy workspace with illustrated actual catalog cards, responsive rail/bottom navigation, clearer private/shared planning, staged reservation/approval/ticket controls and stronger text readability. Existing create/join, seat selection, workshop checkout and isolated rehearsal remain.
- Added `public/guide.js`: four-step interactive walkthrough. Actual room phase explanations and a contextual next-action button explain what happened and what to do next. Unresolved recovery expands automatically. Sound starts muted; removed the decorative ticket tilt.
- Added `public/ai-worker.mjs` and `public/ai.js`: opt-in actual MiniLM embeddings on the device through pinned Transformers.js 3.8.1 and model revision. Model/runtime assets download after explicit enable; inference text stays on the device. Timeouts/asset errors have explicit basic-search fallback. Rankings may contain only the submitted trusted IDs and bounded scores. This is semantic retrieval, not an LLM chatbot or agreement score.
- Added `public/discovery.js`: semantic Vibe Scout, honest keyword mode, actual category/budget/people controls, code-native artwork and exact excursion share previews. It displays catalog data and never generates prices or inventory.
- Added `rescue.py` and the authenticated CSRF-protected `/api/groups/<id>/rescue` route: read-only own-preference counterfactuals. Exact shares, actual roster order, timezone, future schedules, capacity and adjacency are checked with the existing matcher; every other confirmed member stays unchanged. Peer limits are not disclosed. No model/provider call occurs in this calculation.
- Integrated Plan Rescue into `public/room.js`: preview is a visibly unsaved draft; edits clear stale selection/quote and disable matching until explicit confirmation. Optional on-device AI orders only server-verified options by the caller's description. Frozen purchases reject rescue. Domain/group switching clears proposal state.
- Added focused rescue/AI contracts and extended actual-script frontend contracts. CI runs the AI contract too. Documentation now describes the authorized new design and the exact AI-versus-rules boundary.

No schema, dependency, payment protocol, `.env` or credential change in this redesign pass. The existing revision 5 database and prior databases remain in place; no reset, restore or financial mutation was performed. App startup retains its existing migrate/seed-if-empty behavior. Publication is authorized as described above; no merge or deployment.

### Latest evidence

- **132 Python tests passed in 51.633 seconds**, temporary SQLite and mocked providers. Seven new rescue cases cover own-only exact edits, peer privacy, timezone constraints, cent remainder, membership/confirmation/frozen boundaries, unavailable/past inventory and HTTP identity/CSRF.
- Guided frontend contracts passed with mocked DOM/HTTP/SDK: catalog rendering/filtering, walkthrough navigation, no fake keyword results, explicit rescue preview without confirmation, subsequent canonical save, real room/approval/recovery/ticket callbacks and private-state clearing.
- AI contracts passed: lazy loading, initialization readiness, retry, disable, input bounds, no invented/duplicate/missing IDs, invalid scores, keyword fallback, and actual worker request/embedding-cache behavior with mocked embeddings. No inference-service call was made by these tests.
- Twelve isolated solo-demo contract checks passed. HTML nesting, 198 unique IDs and format equivalence checks passed. CSS brace balance and format equivalence checks passed. JavaScript syntax passed for all six new/modified controllers and the worker; Python syntax passed across all 15 application modules. Final localhost HTTP checks passed for exact current HTML/CSS and all seven script files, no-store headers, worker MIME and anonymous rescue denial (401). No session, group, booking or financial provider call was created by these HTTP checks. The existing local server was restarted with its existing configuration at http://localhost:8000.
- Pinned runtime, model config and quantized model asset URLs returned HTTP 200; quantized model length is 22,972,370 bytes. This establishes asset availability, not actual inference compatibility or model quality.
- Computer-use retry again failed before browser launch: kernel-assets path error 3. Rendered desktop/mobile, real-model inference, keyboard/popup behavior, genuine multi-buyer Sandbox, Gemini and PostgreSQL runtime remain unverified. Automated providers/embeddings are mocks.

Review [docs/AI_AND_GUIDED_UX.md](docs/AI_AND_GUIDED_UX.md), then follow [HACKATHON_SHOWCASE.md](HACKATHON_SHOWCASE.md). Before recording, test AI on the actual browser/network, inspect mobile/desktop, and use separate profiles for a genuine saved group. Record real evidence separately from simulations. This work is a review candidate and does not imply winning/acceptance or production readiness.

## Previous integration pass (historical record; publication status below predates this snapshot)

## What this pass changes

The user restored Panchadip's original branch and then authorized fixes to six reproduced gaps. This pass preserves his UI rather than restoring the earlier replacement frontend. Reviewed backend modules and regression tests were selectively reused from the archived correction, then integrated with the original application. No credentials or old databases were copied from that archive.

- Original discovery, create/join dialogs, seat canvas, wallet card, sounds, workshops and architecture walkthrough remain. The former room script was extracted into `public/room.js`; `public/app.js` retains navigation, discovery, dialogs, lab entry points and workshop CAPTURE checkout.
- The room now has progress steps, a contextual next action, privacy settings, separate saved shared chat, private preference review with collapsed advanced fields, exact server quote shares, explicit consent, AUTHORIZE SDK callbacks, saved-order recheck and organizer recovery/cancellation.
- Real snake_case constraints are displayed and edited. The chosen discovery domain reaches the room. Confirmed edits reload canonical preferences and fresh advice. There is no hardcoded 98% agreement, invented default budget or first-offer fallback.
- Group AUTHORIZE and workshop CAPTURE SDKs remain separate. Buyer approval precedes server authorization. Reload restores the reservation's amount and experience; switching groups clears the prior private ticket, QR, consent, messages, preference advice and selection.
- `booking_payments.py`, `booking_lease.py`, `payment_evidence.py` and `booking_errors.py` separate durable coordination, fencing and provider validation. All roster evidence is checked before capture. Pending captures cannot issue tickets. Failed or unknown compensation stays visible and retains inventory. No database transaction spans a provider call.
- `planning.py` and `ai_planner.py` provide bounded interpretation, genuine local fallback without Gemini, confirmed-only matching, actual timezone/budget constraints and meaningful private catalog previews. Server selection validates the real chosen resources.
- `room.py` stores session-authored messages and consent-aware coarse coordination. Sender aliases cannot switch identity. `groups.py` respects alias sharing consent.
- `public/demo.js` keeps fictional personas, three-person teaching view, readiness, Chaos, local ticket ledger and duplicate admission rejection in isolated memory. Original Judge Hub entry points launch that model. All synthetic financial mutation routes are absent from the saved workflow.
- `ticketing.py` uses pinned `qrcode==8.2` to encode an existing owned ticket reference as SVG. Private record verification rejects another member's code. It does not claim cryptographic supplier verification, real admission or wallet integration.
- The guardrail inspector now calls an authenticated, CSRF-protected interpretation-only preview endpoint. It reports the actual response without saving a preference or altering money/inventory. It no longer displays a fabricated all-passed result on initial load.
- Focus indicators, keyboard dialog handling, larger targets, reduced-motion behavior, mobile field layout, no-clipping chat layout and status announcements extend the original style. Guidance consulted: [W3C focus visibility](https://www.w3.org/WAI/WCAG21/Understanding/focus-visible) and [WCAG 2.2](https://www.w3.org/TR/WCAG22/). PayPal integration follows the [v5 authorization flow](https://developer.paypal.com/v5/checkout/auth-capture/). This is not an accessibility conformance claim.

## Modules and migration review

`server.py` remains the authenticated HTTP boundary. Revision 4 adds `group_workflows` and `group_operations`; revision 5 adds `room_messages`. Applied original revisions are unchanged. Legacy revision 3 purchases/tickets are preserved and flagged for merchant review rather than treated as completed captures. No financial data is imported, restored or downgraded.

The previous correction and original restoration backups remain ignored under `../.local-archive/` and `instance/`. The outer Git repository remains separate. The active `.env` selects the original-restoration database; the previous application's revision 5 database is not substituted.

## Verification

- Full integrated Python suite: **125 tests passed in 31.492 seconds**, using temporary SQLite databases and fake payment providers. Includes original workshop contracts, group money/recovery/privacy, pending and mismatched evidence, lost responses, concurrency/fencing, migration preservation, shared chat, ticket encoding/checks and mutation-free inspector behavior.
- `node tests/test_frontend_contract.cjs`: passed. Executes the original app bootstrap, actual room forms, edited canonical budget, shared chat as text, discovery domain selection, no-false-match behavior, exact quote/freeze, separate SDK intents, no authorization before `onApprove`, pending recovery ticket lock, successful ticket display/check and group-switch clearing. DOM, HTTP and SDK are mocked.
- `node tests/test_demo_contract.cjs`: **12 checks passed**. Tests include actual mounted model controls and pending recovery; no financial service is called.
- `pip check`: passed. The added QR dependency is installed in this workspace. JavaScript syntax, static ID consistency and duplicate-ID checks passed.
- Final HTML nesting and Python syntax checks passed across 27 Python files. The frontend regression additionally verifies that an unavailable-seat error remains visible at the top of the room after controls re-render, and that a saved reservation restores its exact total and canvas on reload.
- The running original-restoration SQLite database was identified as revision 3, privately backed up under ignored `instance/before-original-ui-integration-*`, then upgraded to revision 5. All pre-existing table contents were compared before/after and verified unchanged. No data was restored from the previous application's separate database; `.env` and credentials were unchanged. The network-enabled local app was restarted at `http://localhost:8000`.
- Live localhost HTTP checks passed for exact HTML/JS/CSS content (including the new room/demo modules), no-store headers, session/config, catalog, group reads and the interpretation-only probe. Configuration reported local planning mode and configured Sandbox credentials. No purchase, financial provider mutation or live payment completion was performed.
- Browser tool initialization failed with `failed to write kernel assets (os error 3)`. No rendered desktop/mobile, real SDK popup, live multi-buyer capture, real Gemini or PostgreSQL runtime result is claimed.

On this restricted Windows installation, Node is available at `C:/Program Files/Microsoft Visual Studio/2022/Professional/MSBuild/Microsoft/VisualStudio/NodeJs/node.exe`; pass `--preserve-symlinks --preserve-symlinks-main` before either test filename. Normal Node environments need neither flag.

## Collaborator review and next steps

1. Review the original UI diff and `public/room.js` contracts. Run all three suites and the dependency check.
2. Check the actual desktop/mobile layout and keyboard dialogs; verify room switching during in-flight requests and PayPal approval.
3. Rehearse alone in Judge Hub, then test a genuine saved group with separate browser profiles and buyer-approved Sandbox payments. Record exact provider evidence without exposing credentials or session tokens.
4. Verify reload/restart and unresolved recovery. Keep pending outcomes visible; never reset a database to make a scenario succeed.
5. Test real Gemini separately if a key becomes available. The local helper is the supported no-key path.
6. Test managed PostgreSQL and concurrent operations before hosting. Choose the license and record a truthful submission video.

Captures remain sequential and compensation can remain unresolved. Supplier inventory is fictional. Account recovery, real admission, production money, webhooks, post-confirmation customer refunds and multi-merchant onboarding remain outside this implementation. No commit, push, merge or deployment has been performed.
