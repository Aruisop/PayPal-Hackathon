# Adversarial feature audit

**Date:** 28 October 2026
**Code base:** local `dev/aarya` snapshot based on `4fabe98`, plus uncommitted work in this workspace. This is a review candidate, not a release sign-off.

## Findings first

The server-local group recommender is wired and can run real BGE inference without a Gemini key. The active application reports its pinned BGE assets prepared; the weights load lazily on an eligible comparison. A direct local smoke run loaded the model in about 395 ms and encoded two phrases to finite 384-element vectors in about 11 ms. The actual recommendation route has also passed with real BGE weights in the isolated temporary-HTTP/DOM flow.

The reported “AI does not work” experience came from two different problems being presented as one. The saved catalog has no future bookable options, so hard eligibility correctly leaves the model nothing to rank. Separately, Discover and Plan Rescue exposed a second browser MiniLM feature that downloads a runtime from a CDN; its real-browser execution had never been verified and its purpose duplicated the group comparison. That browser model and its controls are removed. Discover now uses explicitly labeled catalog keyword search; the collaborative group recommender is the one semantic AI feature.

The live app cannot demonstrate an end-to-end group recommendation or checkout until future catalog sessions are present. The append-only `python -m app prepare-demo` command is available but has not been run against the saved database. Do not change group preferences to compensate for an empty catalog.

## Feature results

| Feature | Adversarial result | Evidence and remaining limit |
| --- | --- | --- |
| Discover and catalog | Server supplies upcoming/past state and group-size capacity. Search is ordinary keyword matching over title, description, domain and genre; no semantic claim. Empty results distinguish no dates from search/filter misses. | Frontend contract and isolated DOM/API flow pass. Active saved catalog has no future options. Visual browser rendering is still unverified. |
| Group membership and room | Invite membership, per-browser identity, private preferences, opt-in aliases/coarse progress and shared messages stay separate. Peer preference edits invalidate stale comparisons and rescue drafts. | Python service/HTTP tests and live temporary-API DOM flow pass. Cookie identity has no account recovery; this is a hackathon flow, not a full account system. |
| Preference review | No-key parser produces an editable draft; each person explicitly confirms their own structured limits. Blank constraints stay flexible. Gemini remains an optional interpretation path, not a dependency. | Python and frontend contracts pass. Gemini is not exercised and is unnecessary for this demo. English date/time parsing and taste exclusions remain bounded/heuristic. |
| Group AI comparison | Server validates confirmed hard constraints and capacity before embedding. Pinned CPU BGE compares only eligible offers against confirmed positive likes. The default is modeled compromise regret; average and schedule-order views are explicit alternatives. | Actual BGE initialization/vector smoke and real-model recommendation route pass on synthetic temporary data. The active catalog currently produces no eligible request. Five offers and assistant-authored labels do not establish human relevance, satisfaction, fairness or competition superiority. |
| Plan Rescue | Deterministic counterfactual: shows only the caller's own changes that make an actual offer pass while peers remain fixed. Preview is unsaved and requires confirmation. | Seven original Python scenarios plus guided journey checks pass. Hidden when there are no future bookable options; it cannot manufacture inventory or relax peers' constraints. |
| Seat/place selection and exact shares | Server quote/freeze revalidates roster, capacity, adjacency and integer-cent splits. The organizer selects; AI does not reserve. | Booking, quote, cents, stale-state and journey tests pass. Automated provider behavior uses fakes. |
| PayPal group payment and recovery | Each participant consents to and approves their own Sandbox order; authorization is not capture. Organizer capture is gated on all validated authorizations, and tickets wait for all completed captures. Ambiguous operations keep inventory reserved for recovery. | Extensive mocked provider, fencing and recovery tests pass. No real two-buyer Sandbox transaction was run in this audit. Do not claim settlement from these tests. |
| Tickets and admission | Tickets are private application records unlocked after completed captures; the QR encodes the owner record. The checker validates ownership/reference only. | Python/API tests pass. It is not venue admission, a supplier-signed ticket or Apple/Google Wallet integration. |
| Solo Judge Hub | Independent local simulation uses copied catalog data; it does not contact PayPal or mutate saved bookings. | Twelve isolated behavior contracts pass. It demonstrates the state machine, not real payment/provider behavior. |
| Workshop checkout | Existing individual Sandbox checkout and lesson entitlement remain separate from the collaborative group flow. | Workshop tests are part of the Python suite. This is supporting Slice 3 functionality, not the main collaborative novelty. |
| Local deployment | SQLite is suitable for the local demo; production checks require PostgreSQL/HTTPS. BGE weights live in ignored instance storage and must be prepared on any host that needs AI. | Local dependencies and assets are ready here; `pip check` passes. PostgreSQL, hosted model setup, concurrency and production operations are not verified. |

## Repair made in this audit

- The room checks the live catalog snapshot for future bookable options matching the current group size. It disables comparison when there is nothing to rank, hides rescue when no real option can be unlocked, and offers a category switch only when the other category has a bookable option. Full inventory is distinguished from expired/missing dates.
- Removed the second MiniLM browser model, its CDN-dependent worker, its enable/download UI, its Plan Rescue reranker, related routes and redundant worker contract. One model means one explainable comparison path and no ~23 MB browser download during the demo.
- Discover retains straightforward keyword search with clear labels. Removed code that described keyword results as semantic AI.
- Removed the duplicate rules-only room comparison button. The group comparison endpoint already returns verified rules-based matches when semantic ranking is unavailable.
- Updated judge walkthroughs and architecture notes to describe the current controls and evidence, not the removed worker.

## Verification performed

- Full Python suite: **197 tests passed**.
- Frontend interaction contract passed with mocked DOM, HTTP and PayPal SDK; it checks keyword search, no-inventory guidance, explicit preference confirmation, rescue preview and payment/ticket callbacks.
- Solo demo: **12 contract checks passed**.
- Actual DOM plus temporary HTTP app plus real BGE passed the guided group comparison, taste confirmation, stale-state invalidation and tradeoff flow; the mocked frontend contract covers the empty-catalog UI. The live fixture does not render a native browser and blocks all payment-provider access.
- Local BGE smoke encoded real input; active app's authenticated readiness response identifies BGE revision `ea104dacec62c0de699686887e3f920caeb4f3e3` as prepared and lazy-loaded.
- `pip check` and `git diff --check` pass.
- The approved computer-use initialization failed before browser launch with `windows sandbox failed: helper_unknown_error: setup refresh had errors`. Therefore no visual-rendering claim is made. The existing screenshot indicates the previous empty-catalog state was too wordy; current copy has been shortened and irrelevant controls removed, but desktop/mobile visual acceptance still needs a human browser pass.

## Demo gates still open

1. Add future fictional sessions to the saved local catalog through the explicit append-only setup command, then make sure each experience supports the actual test roster. This has not been run because the active database is under preservation instructions.
2. With two distinct Sandbox buyers, complete one real two-profile approval/capture/reload test. Existing app session profiles are not substitutes for PayPal buyer accounts.
3. Review the rendered app at desktop and narrow mobile sizes. Check focus order, long text, empty/error states and a slow model load.
4. Gather human relevance/usefulness judgments before claiming the algorithm improves group outcomes. Current evaluations are tiny, synthetic and were used for model selection.
5. If submitting to hosted infrastructure, verify BGE setup, managed PostgreSQL, HTTPS, concurrent booking/recovery and operator recovery procedures.

No saved offer, inventory, group preference, booking, payment or ticket was deliberately edited by this implementation. One read of the live authenticated config endpoint created an ordinary empty participant session; no group or financial records were created by that check. At the 28 October audit cutoff, the changes had not yet been committed or pushed; publication is recorded in [Aarya_changes.md](../Aarya_changes.md).
