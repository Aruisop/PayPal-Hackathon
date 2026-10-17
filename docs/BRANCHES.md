# Branch map and delivery status

Snapshot: 11 October 2026. Check `git branch --show-current`, `git status --short`, and `git log -5 --oneline` when joining work. A branch name identifies scope; the status below identifies acceptance.

| Branch | Delivered scope | Status / evidence |
| --- | --- | --- |
| `master` / `origin/master` | Earlier retail Sandbox checkout and startup/account guides, through `5f5c813` | Legacy baseline. Does not contain persistent workshop Slice 1 until a reviewed merge occurs. |
| `slice/1-persistent-workshop-checkout` | Two scheduled fixed-price USD workshops; participant sessions; durable bookings/attempts; safe create/capture retries; protected lesson; owner recovery after verified PayPal approval; mock tests; storage/review docs; contributor workflow and CI | User accepted as the development base on 11 October 2026. Historical Sandbox completion/access/isolation/restart results are user-observed. External architecture signoff is not claimed. See [Slice 1 evidence](SLICE1_REVIEW.md). |
| `slice/2-group-coordination` | Persistent groups/memberships and invites, organizer-only one-time workshop selection, member-specific views into their existing checkout | Implemented review candidate based on Slice 1. AI, pooled payments, seat limits and checkout redesign are excluded. See [Slice 2 review](SLICE2_REVIEW.md). |
| `slice/3-collaborative-booking-and-equal-payments` | Collaborative booking & equal payments: multi-buyer peer-to-merchant authorizations (`intent="AUTHORIZE"`), exact integer cent distribution ($T = \sum c_i$), Gemini AI mediation with 12 safety gates, sequential capture with operation fencing, private digital passes with SVG QR codes, Chaos Lab with compensatory rollback, and a simulated pre-payment readiness card (demo data, no PayPal calls) | Implemented review candidate; review pending. 77 automated tests passing against a fake PayPal adapter. No real Sandbox multi-buyer run is recorded. Demo flows (1-click, simulate authorizations, readiness card) use generated IDs; see the real-vs-simulated table in [README.md](../README.md). |
| `original-history-backup` (local only) | Earlier inherited history backup | Not a delivery branch. Do not push, merge or use as the workshop implementation base. |

## Slice 1 delivery contract

Delivered: individual purchases at $25/$18 USD, SQLite locally, PostgreSQL-compatible versioned schema with durable managed-hosting plan, server-owned pricing, participant ownership checks, completed-capture entitlement validation, stable request IDs, persistent active attempts and explicit reconciliation. After reload, an `AWAITING_APPROVAL` booking is reconciled with PayPal; its owner can explicitly complete the saved approved order using the existing capture path. SDK v5 and vanilla browser code are retained.

Slice 1 did not deliver groups/invitations, preference interpretation, recommendations/AI, merchant dashboard, seat caps, background reconciliation/webhooks, account recovery, refunds/revocation, SDK v6, production payments or a hosted PostgreSQL demo. Slice 2 adds only groups/invitations. Expired unapproved orders with ambiguous evidence remain locked; a replacement recovery mechanism is not implemented.

## Commit organization on this branch

The delivery is separated into a checkout/review delivery checkpoint and a CI/review-workflow checkpoint. Read commit subjects with `git log --oneline origin/master..HEAD`. Existing planning work is preserved and explicitly marked historical/proposed; it is not represented as shipped functionality. The GitHub branch replaces the removed ZIP as the review artifact.

## Future branch conventions

| Pattern | Intended use | Base and boundary |
| --- | --- | --- |
| `fix/slice1-<problem>` | Authorized correction to the current payment slice | Slice 1 remote tip; retain the payment contract and update tests/evidence |
| `docs/<topic>` | Onboarding, evidence or architecture clarification | Relevant reviewed branch; no feature expansion |
| `slice/<number>-<outcome>` | Next explicitly authorized vertical slice | Latest approved implementation base; document scope and acceptance |
| `chore/paypal-sdk-v6` | Separately approved SDK migration | Approved checkout base; do not combine with payment-state redesign |

Group coordination is delivered only on `slice/2-group-coordination` for review. AI work remains a future proposal, with no AI implementation branch.

## Documentation authority

1. [README](../README.md): current setup and implemented scope.
2. [Slice 2 review](SLICE2_REVIEW.md): group scope, evidence and limitations; [Slice 1 review](SLICE1_REVIEW.md): payment state model and historical evidence.
3. [Storage decision](STORAGE_HOSTING.md): local/hosted persistence requirements.
4. [Development guide](DEVELOPMENT_GUIDE.md), [CONTRIBUTING](../CONTRIBUTING.md), [AGENTS](../AGENTS.md): integration and collaboration practices.
5. [Phase 0](WORKSHOP_PHASE0_REVIEW.md): original workshop proposal; corrections and implemented scope are in the Slice 1 review.
6. [Earlier retail guide](history/RETAIL_DEVELOPMENT_GUIDE.md), [product ideas](PRODUCT_DIRECTION.md), [video feasibility](FEASIBILITY.md): historical context, not current implementation or future-work authorization.

When scope/status changes, update this map and the README in the same change. Keep a reviewed slice's evidence intact rather than relabeling every green test run as acceptance.
