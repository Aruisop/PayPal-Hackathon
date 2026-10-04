# Individual workshop purchase: review packet

Implemented 4 October 2026. Stop point: this slice only; groups, AI preferences, recommendations, merchant dashboards, seats and SDK v6 are not implemented.

## Changes and preservation

Before work, `docs/DEVELOPMENT_GUIDE.md` was modified, and `docs/FEASIBILITY.md`, `docs/PRODUCT_DIRECTION.md`, and `docs/WORKSHOP_PHASE0_REVIEW.md` were untracked. All four were preserved during Slice 1 implementation. For branch publication, the older development guide (including its uncommitted planning link) was retained in `docs/history/RETAIL_DEVELOPMENT_GUIDE.md`; a new current guide replaces it, and planning documents receive explicit historical/proposal labels. The agent did not edit credentials or `.env`; the user subsequently added an optional Merchant ID locally. The payment implementation and manual evidence were prepared before branch publication; the later GitHub handoff is described at the end of this report. Historical planning/setup guides retain earlier retail context; the current README and this packet govern Slice 1.

Changed tracked files: `server.py`, the three `public/` files, `.env.example`, `.gitignore`, and `README.md`. The obsolete seven-test retail fixture in `tests/test_checkout.py` was replaced by `tests/test_workshop_slice.py` for the actual workshop contract.

New code: `payments.py` (extracted/extended urllib adapter), `storage.py` (SQLAlchemy Core schema/migration/store), `checkout.py` (payment orchestration), and pinned `requirements.txt`. New documentation: this review and `STORAGE_HOSTING.md`.

The slice replaced the older checkout tests and added persistent checkout/storage/provider modules, pinned requirements and review/storage documentation. Review close-out changed only this report and one expiry regression test, with payment implementation unchanged. GitHub handoff adds branch/contributor/agent guidance, a PR template and mock-only CI. Before staging, `git diff --stat` omits untracked additions; review the final committed tree/diff for the complete delivery.

The earlier proposal's SQLite-only persistence is adjusted to SQLAlchemy Core plus PostgreSQL-compatible revision 1. Flask replaces the bespoke HTTP router; Python and vanilla browser code remain. SDK v5 and its create/onApprove callbacks are retained exactly as the review directed. The local virtual environment and database are ignored by Git.

## Data model and authorization

Revision 1 contains `participants`, `workshops`, `bookings`, `payment_attempts`, and `entitlements`, plus `schema_versions`. The application provides a versioned `python server.py migrate` command for SQLite and PostgreSQL. Revision 1 is immutable; subsequent schema changes need another explicit migration.

- Server-generated 256-bit session tokens identify participants. Only token hashes are stored, alongside a CSRF token and 30-day expiry. The cookie is HttpOnly/SameSite Strict; production requires Secure cookies.
- A booking is unique by participant and scheduled workshop. A nullable `future_membership_id` allows a later group association without implementing groups now.
- A booking points to one active payment attempt. Earlier denied attempts remain recorded. Create/capture request IDs, price/currency snapshots, provider IDs, timestamps, and operation leases persist in the database. An optional expected merchant is recorded initially; otherwise the merchant field starts empty and is populated from an authenticated order GET before capture. The returned seller is then pinned for subsequent validation.
- Atomic lease claims coordinate concurrent operations. A lease lasts 120 seconds. Writes are fenced by lease token and expiry. A crash can temporarily show an in-progress record until the lease expires; recheck is then available.
- Entitlements are unique by booking/capture and granted in the same transaction as booking confirmation. Every receipt, capture, recheck, cancellation and lesson route checks the current participant's ownership. Order IDs alone never authorize access.

Catalog prices are $25 and $18 USD, with two one-hour scheduled online workshops. The first seed sets concrete future Sunday dates; later restarts preserve them. Catalog fields are merchant-controlled database records. There is no browser-side price authority or catalog editor.

## Implemented states and retries

Booking states: `PAYMENT_IN_PROGRESS`, `UNPAID` after safe cancellation/denial, and `CONFIRMED` only after completed capture validation.

Attempt states: `CREATING`, `AWAITING_APPROVAL`, `APPROVED`, `CAPTURING`, `PENDING`, `UNKNOWN`, `DENIED`, `CANCELLED`, `COMPLETED`.

| Observation | Implemented behavior |
| --- | --- |
| First initiation | Persist booking, attempt, price snapshot, optional seller pin and both request IDs before order creation; persist returned merchant from authenticated GET before capture |
| Double initiation or refresh | Same participant/workshop booking and active attempt; no fresh purchase |
| Buyer approval only | No entitlement; capture still required |
| Completed capture | Authenticated order GET validates booking reference, merchant and amount; capture amount/status checked; confirm and grant atomically |
| Capture response omits merchant/correlation | Authenticated order GET supplies trusted correlation; never grant from browser approval |
| Pending capture | Persist capture ID, access locked; recheck uses order/capture GET, not another charge |
| Capture response lost | Query provider order immediately; known capture ID can be queried independently |
| Unresolved capture | Manual recheck queries current provider state before a same-key retry inside the six-hour window; no replacement order |
| Unknown creation without order ID | Recheck replays the stored create key only inside six hours; beyond that, remain unresolved |
| Definitive decline | Access locked; after reconciliation, a guarded replacement attempt may be created on the same booking |
| Cancel before capture | Mark cancelled and resume the same unapproved order; do not replace it with a second purchase |
| Cancel while pending/unknown/capturing | Does not overwrite payment state |
| Expired unapproved order with ambiguous provider lookup | Keep the same attempt/order unresolved and lesson locked; no replacement purchase or capture |
| Completed booking, including beyond provider retention | Permanent application uniqueness returns the same paid booking; no new order |

No transaction spans OAuth, order creation, capture, order GET or capture GET. Completed receipts remain local durable facts. Provider mismatch, missing required data, unknown status, throttling or network failure cannot grant access.

### Idempotency evidence

Official endpoint-specific create and capture documentation states six-hour default `PayPal-Request-Id` retention, with account-manager extension possible. This code assumes only six hours. The same key/payload is reused for retryable operations within that window; uncertain attempts remain blocked after it. Application uniqueness and completed-booking protection have no six-hour expiry.

- [Create-order header contract](https://developer.paypal.com/sdk/orders/v2/orders-create/)
- [Capture-order header contract](https://developer.paypal.com/sdk/orders/v2/orders-capture/)
- [PayPal idempotency, including simultaneous-request limitations](https://developer.paypal.com/api/rest/reference/idempotency/)
- [PayPal-owned OpenAPI specification](https://raw.githubusercontent.com/paypal/paypal-rest-api-specifications/main/openapi/checkout_orders_v2.json)

Both POSTs request `Prefer: return=representation`. A pending/unknown attempt is never replaced merely because another browser request arrived or provider idempotency expired.

## Test and evidence results

Command: `.venv\Scripts\python.exe -m unittest discover -s tests -v`

**26 tests passed** (3.192 seconds in the close-out run). They cover trusted pricing despite tampered amounts/currency/merchant, duplicate and four-worker concurrent create/capture, approval-only denial, completed versus pending access, lost capture response, known capture ID with omitted order capture list, capture ID persistence before a failing detail request, server restart and cookie persistence, private booking/receipt/lesson/capture ownership, provider merchant/amount/booking mismatches, cancellation and decline, CSRF/origin/session rejection, six-hour expiry guards, stable-key recovery, expired-worker fencing, no database transaction across PayPal calls, production rejection of SQLite, checkout without a Merchant ID setting while persisting and enforcing the returned seller, and an expired unapproved order with ambiguous provider evidence remaining locked without replacement.

`pip check` passed. Python compilation and local migration passed. PostgreSQL schema compilation produced six valid DDL statements; this is **not** execution against a PostgreSQL server. Static frontend ID checks and preservation of the v5 SDK URL passed. Browser/runtime tooling could not initialize (`failed to write kernel assets`), so agent-operated browser interaction and visual verification remain unperformed. User-observed browser results are recorded separately below.

Automated payment tests use a fake PayPal service maintaining external order state independently of the application database. They do not constitute Sandbox purchase evidence.

A real local Waitress HTTP smoke check passed for the catalog, three static routes, HttpOnly session issuance and anonymous booking denial. The exact saved Client ID/Secret values were absent from commit-visible files; `.env` and `instance/workshops.db` were confirmed ignored. `git diff --check` passed. This checks current files, not the entire historical Git object database.

### Real Sandbox evidence and user-observed manual results

Evidence provenance matters: the agent independently checked Sandbox OAuth and prepared a real Sandbox order by retrying an existing saved create request. The agent did not approve or capture a buyer payment, independently query the completed capture, or operate the two browser profiles. OAuth success establishes API credential/connectivity validity, not a completed purchase. No additional Sandbox transaction was initiated during this close-out.

On 4 October 2026, the user supplied the completed booking JSON and screenshots, then reported the separate-profile and restart checks. Record these as **user-observed checks**, not independently agent-verified results:

| Manual check | User-observed result |
| --- | --- |
| Sandbox purchase | Coding interviews workshop, $25.00 USD; booking `CONFIRMED`, payment `COMPLETED` |
| Buyer lesson access | The paid participant opened the protected sample lesson successfully |
| Separate unpaid profile | After establishing its own participant session, the separate unpaid browser profile received `BOOKING_NOT_FOUND` for both the buyer's receipt and lesson |
| Persistence after restart | The user reported the paid booking and lesson access persisted after restarting the server |

User-supplied identifiers: booking `4d20143943de25d9d392d570824e0723`, PayPal order `525405084S166681B`, capture `16M933080E946661S`. These are transaction identifiers, not session cookies or API credentials. The initial unauthenticated private-window response was `PARTICIPANT_SESSION_REQUIRED`; that alone was not participant-isolation evidence. The user subsequently confirmed denial after establishing a distinct unpaid session.

The user-reported results establish manual buyer-path, participant-isolation and persistence evidence for this slice. They do not constitute independent agent verification of PayPal settlement. Seller-dashboard activity and an independent provider lookup of the completed capture have not been recorded here. Automated failure cases remain mocks. Earlier retail-demo purchases are not used as evidence for this workshop path.

The optional `PAYPAL_MERCHANT_ID` setting remains a seller-validation pin, as described below. During manual verification, a restricted local server connection produced `PAYPAL_UNAVAILABLE`; an unrestricted OAuth check passed, and retrying the existing booking's persisted create key prepared its Sandbox checkout without a capture. This runtime diagnosis changed no payment source code or entitlement rules.

## Merchant ID correction for external review

`PAYPAL_MERCHANT_ID` was originally mandatory in `PayPal.configured`, copied into each attempt, sent as `purchase_units[0].payee.merchant_id` by `Checkout.initiate`, and compared in `Checkout._validate_order`. That was an application-imposed validation/routing requirement, not a Standard Checkout prerequisite.

PayPal states that omitting `payee` selects the API caller's account ([official payee behavior](https://developer.paypal.com/platforms/checkout/standard/customize/multiseller-payments)). The [Standard Checkout integration](https://developer.paypal.com/platforms/checkout/standard/integrate) creates orders using app credentials. For this single-merchant slice, the blocker is removed: only Client ID and Secret enable checkout; `POST /v2/checkout/orders` omits `payee`; `GET /v2/checkout/orders/{id}` supplies the seller. The code validates order ID, booking reference and amount/currency, persists the nonempty returned merchant ID before capture, and enforces that same merchant on later observations. An optional configured Merchant ID is an additional expected-seller pin, never a routing override.

Exact functions: `payments.py:PayPal.configured`, `payments.py:PayPal.create_order`, `payments.py:PayPal.get_order`, `checkout.py:Checkout.initiate`, `checkout.py:Checkout._validate_order`, and `checkout.py:Checkout._observe`. Capture remains `POST /v2/checkout/orders/{id}/capture`. Missing/mismatched provider seller data cannot grant access. No schema revision changes: revision 1's non-null merchant field uses an empty string until discovery.

This packaging correction and its regression test are the only payment changes made after the pause request. README, environment template, setup message and hosting instructions were updated. At that initial packaging step, no group/AI work, new Sandbox order, commit, push or deployment was performed. Later Sandbox verification is recorded above with its evidence provenance.

## Hosting and storage

[STORAGE_HOSTING.md](STORAGE_HOSTING.md) was written before implementation selection. Local SQLite is an ignored persistent file; hosted judges use a separately provisioned paid managed PostgreSQL database, not an ephemeral web-service file or expiring free database.

Set `DATABASE_URL`, `APP_ENV=production`, an exact HTTPS `APP_ORIGIN`, `COOKIE_SECURE=true`, and private app credentials (optional expected Merchant ID pin). Run `python server.py migrate` before starting the Waitress web process. The app rejects production SQLite and insecure production origin/cookie settings. Database lifecycle and backups must remain separate from web redeploys. No managed service was provisioned, and PostgreSQL execution remains unverified.

## Two-profile manual walkthrough

1. Install requirements using the README's virtual environment commands. Preserve the existing `.env`; set the Business Sandbox app Client ID and Secret. `PAYPAL_MERCHANT_ID` is optional. If supplied, it must match the app's seller; an incorrect pin blocks capture/access. Save and restart.
2. Run migration and start the app. Use the exact configured `APP_ORIGIN` (default `http://localhost:8000`). Stop an old server on that port first, or change both PORT and APP_ORIGIN together.
3. Open profile A and separate profile B. Do not use two ordinary tabs sharing a cookie. Both should see the two scheduled workshops and no private bookings belonging to the other profile.
4. In A, select a workshop, click PayPal and use the US Personal Sandbox buyer with the existing IN seller. Approve the exact displayed USD price.
5. Require `COMPLETED` capture and `CONFIRMED` booking, with order/capture IDs, then open the lesson. Confirm that capture in the seller's Business Sandbox activity.
6. Copy A's `/api/bookings/<id>` and `/lessons/<id>` URLs into B. Expect 404; B's own booking list must not contain A's receipt. If B creates its own unpaid booking for the same workshop, B's own lesson returns 403.
7. Refresh A, then restart the server without deleting its database. A should retain the same receipt and access. Initiating the same workshop again must return the existing paid booking, not another purchase.
8. Cancel an unpaid checkout and resume: it should reuse the order. For pending/lost-response fault behavior, run the automated fake tests; do not misrepresent those as live Sandbox outcomes.

Record the real order ID, capture ID, verified merchant/amount/currency, A's successful lesson status, B's denied responses, and restart result in a private verification note without session cookies or credentials. Only then label the end-to-end workshop purchase verified.

## Known limitations and follow-ups

- Session identity lasts 30 days and is tied to this browser cookie; no login, account recovery or cross-device migration. Clearing/expiring a cookie does not erase a booking but prevents this demo identity from retrieving it.
- Unresolved payments are reconciled on explicit actions, not a background worker/webhook. Browser polling reads stored status only. Persisted unknown outcomes beyond safe retry windows require merchant investigation; there is deliberately no reset button that risks a second charge.
- Expired unapproved orders are a known usability limitation: if provider lookup is missing/ambiguous, the application remains unresolved and lesson access stays locked. Expiry or `RESOURCE_NOT_FOUND` alone does not prove that a replacement purchase is safe. The existing attempt, order ID and request IDs must be retained; no replacement order is created on that evidence. This slice deliberately adds no speculative recovery/reset mechanism. The focused mock regression `test_expired_unapproved_order_missing_at_provider_stays_locked` verifies recheck, repeat initiation and capture requests cannot create a replacement, capture funds or grant lesson access.
- No refunds/reversals, entitlement revocation, webhooks or production payments. Completed local facts are not continuously monitored for later reversals.
- No live PostgreSQL integration, hosted deployment or agent-operated browser test. Completed Sandbox purchase, buyer access, separate-profile denial and persistence are user-observed; independent provider verification of the completed capture and seller activity remain unperformed.
- Versioned migration 1 supports both dialects structurally, but future revisions and managed database deployment must be tested before hosting. Run migrations through one controlled deployment step.
- No catalog admin/date-rotation interface. Seeded dates stay fixed; a later demo requires new offerings through a reviewed migration rather than rewriting purchased offerings.
- SDK v6 migration is a separate follow-up. Group/preferences/AI remain the intended product and were not implemented here. This payment slice alone is not the complete hackathon entry.

Slice 1 implementation and acceptance are separate: publication on its review branch does not constitute architecture acceptance or deployment. Group and AI implementation remain paused.

## GitHub review handoff

The generated review ZIP was removed at the user's request. No archive is part of this GitHub delivery; `review-artifacts/` is ignored. The review source is branch `slice/1-persistent-workshop-checkout`, based on legacy `master` at `5f5c813`. The default branch and its earlier retail demo are not changed or merged by this handoff.

Read [BRANCHES.md](BRANCHES.md) for branch scope and acceptance status, [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) for the current code map/pitfalls, [CONTRIBUTING.md](../CONTRIBUTING.md) for focused branch/PR workflows, and [AGENTS.md](../AGENTS.md) for AI contributor instructions. The older retail guide is preserved under `docs/history/`; earlier product/feasibility documents are explicitly historical. Contributor guidance and CI do not implement group/AI features or a new payment recovery mechanism.

Publishing uses explicit source/documentation paths. Saved credential values are checked against staged files and reachable branch history without printing them; `.env`, API secrets, session cookies, databases, virtual environments, caches and generated archives are excluded. The local history-backup branch is not pushed. Mock-only GitHub CI installs pinned dependencies, checks them and runs the unittest suite on Python 3.10/3.12. Local validation is recorded above; a workflow definition does not claim a successful remote run, hosted PostgreSQL validation or new Sandbox transaction.

Development of group/AI features remains paused. This branch is implemented and published for external architecture review; Slice 1 acceptance remains the reviewer's decision. No merge, default-branch change or deployment is part of this handoff.
