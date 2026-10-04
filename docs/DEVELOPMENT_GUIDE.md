# Workshop Slice 1 development guide

This guide describes `slice/1-persistent-workshop-checkout`, not the legacy retail demo on `master`. Architecture acceptance is pending. Start with [README](../README.md), [branch map](BRANCHES.md), [review packet](SLICE1_REVIEW.md), and [contributor workflow](../CONTRIBUTING.md). The previous guide, including its uncommitted planning link, is preserved in [history](history/RETAIL_DEVELOPMENT_GUIDE.md).

## Code map

| File | Responsibility |
| --- | --- |
| `server.py` | Flask routes, persistent participant session issuance, origin/CSRF/ownership enforcement, private lesson response, Waitress and migration CLI |
| `storage.py` | SQLAlchemy Core revision 1, trusted two-workshop seed, participants, bookings, attempts and entitlements; SQLite/PostgreSQL selection |
| `checkout.py` | Payment state transitions, operation leases, uniqueness, create/capture/reconcile/cancel, authenticated provider validation and entitlement checks |
| `payments.py` | Sandbox-only OAuth and Orders/Payments HTTP adapter; request-ID headers and uncertainty-aware errors |
| `public/` | Plain browser UI and PayPal SDK v5 Buttons callbacks; no frontend framework/build step |
| `tests/test_workshop_slice.py` | Independent fake-provider state and 26 payment/authorization/persistence regression tests |
| `requirements.txt`, `.env.example` | Pinned Python dependencies and credential-free environment template |

## Request path and integration boundaries

Loading `/api/config` issues or resumes a participant cookie, returns its CSRF token, and loads catalog/own bookings. Selecting a workshop creates no entitlement. `POST /api/orders` accepts workshop identity and derives price/currency from the catalog. The service persists the booking, active attempt and request IDs, then calls PayPal outside a database transaction. Orders omit explicit payee routing; the authenticated provider order supplies a persisted seller ID. An optional configured Merchant ID is only an expected-seller validation pin.

The v5 `onApprove` callback requests capture. The backend validates order/booking/merchant/amount/currency, persists operation state, captures or reconciles, and only grants access on a validated `COMPLETED` capture. Private booking/receipt/capture/recheck/cancel/lesson routes require the owning participant. Another participant's order ID or booking URL grants no access.

Each participant/workshop pair has one booking and one active attempt. Definite declines can preserve history and create a guarded new attempt. Pending or ambiguous outcomes cannot create a replacement purchase. GET polling reads stored status; explicit recheck performs reconciliation. There is no background worker or webhook.

## Local setup and pitfalls

Follow the README's virtual environment, dependency install, `.env` and migrate/start commands. Preserve an existing `.env`. Required credentials are the Business Sandbox app Client ID/Secret; buyer credentials belong only in PayPal's browser checkout. Use the exact `APP_ORIGIN`; default is `http://localhost:8000`. Stop an old process before restarting changed code. A restricted execution environment can prevent PayPal network calls; diagnose connectivity without deleting payment state or exposing secrets.

SQLite lives in ignored `instance/workshops.db`; no Docker is required. Browser cookies identify participants for 30 days, with no account recovery. Separate ordinary tabs share identity; use different profiles or a fresh private window for isolation tests. Visit the home page first to establish the unpaid session before testing another participant's private URLs.

Never delete/reset the database to recover an uncertain payment. An expired unapproved order with ambiguous provider evidence remains locked; no replacement recovery is designed here. Seeded schedules are fixed at first initialization. Do not rewrite purchased catalog rows to move a demo date. Future schema changes require new explicit migrations; hosted deployment must use durable managed PostgreSQL as described in [STORAGE_HOSTING](STORAGE_HOSTING.md).

## Verification and handoff

Run the unittest suite and dependency check using the README's environment. Automated provider responses are mocked and never require PayPal credentials. Current manual Sandbox completion, buyer lesson access, separate-profile denial and restart persistence are user-observed checks, not independent agent verification. Hosted PostgreSQL and agent-operated browser evidence remain outstanding; see the review report for the exact limits.

SDK v6 migration, groups/preferences/AI, account recovery and payment recovery redesign are separate future tasks. Read [AGENTS](../AGENTS.md) for invariants and [CONTRIBUTING](../CONTRIBUTING.md) for focused branches and PR handoff. Publishing this review branch does not merge or accept Slice 1.
