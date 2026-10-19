# Contributor instructions for AI agents

These instructions apply to this repository. Explicit user instructions take precedence.

## Establish context

1. Run `git branch --show-current` and `git status --short`. Preserve existing work, credentials, databases and nested repository boundaries.
2. Read `README.md`, `docs/BRANCHES.md`, `docs/DEVELOPMENT_GUIDE.md`, `docs/SLICE3_REVIEW.md` and `Aarya_changes.md`.
3. Follow `CONTRIBUTING.md`; historical Slice 1/2 packets and the proposed PRD do not override current code or evidence.

The current scope is the user-authorized guided redesign and key-free AI extension of Panchadip's Slice 3 integration. The user explicitly requested a new UI after the original-style integration. Keep the light/navy responsive workspace, walkthrough, private/shared room separation, adjacent-place canvas, individual approval, workshops and isolated lab. `public/room.js` owns saved coordination; `public/demo.js` owns simulation; `public/discovery.js` owns catalog presentation; `public/ai.js` and `public/ai-worker.mjs` own optional on-device semantic ranking; `rescue.py` owns read-only verified own-preference tradeoffs. AI never owns consent, confirmed preferences, prices, inventory or payment state. Do not reintroduce either obsolete frontend. The user authorized the UI snapshot and subsequently the accumulated AI/usability changes on `Aruisop/PayPal-Hackathon` branch `dev/aarya`. It remains a review candidate, with browser rendering, browser-worker execution and live payment evidence unverified. The recommendation candidate has real local CPU inference and synthetic benchmarking. `recommendations.py` owns verified semantic regret/average comparisons; `semantic.py` owns optional local encoding; `model_assets.py` prepares pinned assets explicitly. User preference makes compromise the default. Never describe synthetic labels as human-reviewed accuracy, or cosine/regret as satisfaction. Inference must not hold a DB connection and must reject a changed snapshot after completion. Keep Python, SQLAlchemy Core, SDK v5 and vanilla browser code, with explicit modules and focused tests.

## Payment, identity and planning invariants

- Price, currency, merchant mapping, inventory and quote identity are server-owned. AI and clients cannot override them.
- Require membership and participant ownership on every private route. An order ID or invite is not payment authorization.
- Only fully validated completed captures for every frozen contribution may confirm a shared purchase and unlock tickets. Approval, authorization, pending and unknown outcomes do not.
- Persist purchases, contributions, stable operation request IDs and known provider IDs before retryable external operations. Preserve active-purchase uniqueness after provider idempotency expires.
- Reconcile known provider evidence before retrying. Ambiguous evidence cannot authorize a replacement purchase, release uncertain inventory, or unlock tickets.
- Never hold a database transaction across a PayPal call. Enforce operation lease tokens and expiry on state writes.
- Cancellation before confirmation is organizer-only. Confirmed purchase refunds/revocation require separate design; do not free confirmed inventory through the pre-confirmation cancel path.
- Failed/unknown voids or refunds remain durable and visible until confirmed. A queued or attempted refund is not a completed refund.
- Read-only GET requests must not initiate provider mutations. Recovery is an explicit authenticated action or bounded operator command.
- Confirm and validate structured member preferences before matching. Show conflicts, clarification needs, and actual model/fallback mode; never fabricate agreement or confidence.
- Simulations must not mutate real inventory, consent, payment or ticket state.
- Local SQLite is not hosted storage. Use managed PostgreSQL for hosting, and never rewrite an applied migration revision.

## Verification and handoff

From this nested repository, run `..\.venv\Scripts\python.exe -B -m unittest discover -s tests -v` on this workspace, or `python -m unittest discover -s tests -v` in an activated environment. Run `python -m pip check` after dependency changes. Add focused behavioral regressions for money, identity and state transitions.

Run the frontend, demo and AI Node contracts listed in README. Automated PayPal tests are mocks; AI embeddings in automated tests are mocked too. Distinguish them from live Sandbox, real model, PostgreSQL and user-observed browser evidence. OAuth success is not payment evidence. Do not initiate live Sandbox purchases merely to run automated tests.

Never print or commit `.env`, API secrets, session cookies, databases, local credential files or generated archives. `.env.example` contains placeholders only. Use the existing Git identity. Push only a specifically requested branch, never all branches or history backups. Merge and deployment are separate actions.

Keep current docs and `Aarya_changes.md` aligned with the final code. A handoff names branch/base, files, behavior changes, test results, evidence provenance and remaining limitations. Passing tests do not establish acceptance.
