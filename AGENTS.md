# Contributor instructions for AI agents

These instructions apply to this repository. Explicit user instructions take precedence.

## Establish context before editing

1. Run `git branch --show-current` and `git status --short`. Preserve existing uncommitted work.
2. Read `README.md`, `docs/BRANCHES.md`, `docs/DEVELOPMENT_GUIDE.md`, and `docs/SLICE1_REVIEW.md`.
3. Follow `CONTRIBUTING.md` for branches, validation and handoff. The branch map distinguishes delivered code, review status and future proposals.

The current delivery is group coordination on `slice/2-group-coordination`, based on the user-accepted Slice 1 development base. Slice 2 review is pending. Groups and memberships are implemented; preference interpretation/AI, SDK v6, merchant dashboards and broader payment recovery redesign remain future work. The narrow post-approval recovery path is documented in the Slice 1 review. Documents explicitly marked historical/proposed must not override current code or the current slice reports.

## Payment and identity invariants

- Catalog price/currency/workshop identity are server-owned; ignore client-supplied amounts.
- An order ID is not authorization. Require participant ownership on every private route.
- Only a validated completed capture grants an entitlement. Approval, pending, denial, cancellation and unknown outcomes do not.
- Persist booking, attempt, stable create/capture request IDs and known provider IDs before retryable external operations. Preserve active-attempt uniqueness after provider idempotency expires.
- Reconcile known orders/captures before retrying. Ambiguous provider evidence, including an expired unapproved order missing at the provider, must not trigger a replacement purchase or unlock access.
- Never hold a database transaction across a PayPal network call. Preserve operation lease fencing.
- Keep SDK v5 and vanilla browser code for this slice. Hosted storage is durable managed PostgreSQL; SQLite is local only. Applied migration revisions must not be silently changed.

## Verification and evidence

Run `.venv\Scripts\python.exe -m unittest discover -s tests -v` on Windows, or `python -m unittest discover -s tests -v` in an activated environment. Run `python -m pip check` after dependency changes. Add focused tests for changed behavior, not broad implementation-mirroring tests.

Automated PayPal tests are mocks. Distinguish them from real Sandbox requests and user-observed manual checks. OAuth success is not payment evidence. Do not initiate live Sandbox purchases solely to run automated tests.

Never print or commit `.env`, API secrets, session cookies, databases, local credential files or generated archives. `.env.example` contains names/placeholders only. Use the existing Git identity; do not change global Git configuration. Push only the requested branch, never all branches or the local history backup. Merge/deployment are separate from publishing a review branch.

Keep README, branch status and review evidence consistent with changes. A handoff names the branch, delivered scope, files changed, test results, evidence provenance and remaining limitations. Do not mark a slice accepted merely because tests pass.
