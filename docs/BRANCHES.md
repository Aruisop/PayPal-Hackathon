# Branch map and delivery status

Snapshot: 4 October 2026. Check `git branch --show-current`, `git status --short`, and `git log -5 --oneline` when joining work. A branch name identifies scope; the status below identifies acceptance. Future branch patterns are conventions, not claims that those branches or features exist.

| Branch | Delivered scope | Status / evidence |
| --- | --- | --- |
| `master` / `origin/master` | Earlier retail Sandbox checkout and startup/account guides, through `5f5c813` | Legacy baseline. Does not contain persistent workshop Slice 1 until a reviewed merge occurs. |
| `slice/1-persistent-workshop-checkout` | Two scheduled fixed-price USD workshops; participant sessions; durable bookings/attempts; safe create/capture retries; protected lesson; owner recovery after verified PayPal approval; mock tests; storage/review docs; contributor workflow and CI | Implemented review candidate. Architecture acceptance pending. 30 local tests passed; Sandbox completion/access/isolation/restart results are user-observed. See [evidence and limitations](SLICE1_REVIEW.md). |
| `original-history-backup` (local only) | Earlier inherited history backup | Not a delivery branch. Do not push, merge or use as the workshop implementation base. |

## Slice 1 delivery contract

Delivered: individual purchases at $25/$18 USD, SQLite locally, PostgreSQL-compatible versioned schema with durable managed-hosting plan, server-owned pricing, participant ownership checks, completed-capture entitlement validation, stable request IDs, persistent active attempts and explicit reconciliation. After reload, an `AWAITING_APPROVAL` booking is reconciled with PayPal; its owner can explicitly complete the saved approved order using the existing capture path. SDK v5 and vanilla browser code are retained.

Not delivered: groups/invitations, preference interpretation, recommendations/AI, merchant dashboard, seat caps, background reconciliation/webhooks, account recovery, refunds/revocation, SDK v6, production payments or a hosted PostgreSQL demo. Expired unapproved orders with ambiguous evidence remain locked; a replacement recovery mechanism is not implemented.

## Commit organization on this branch

The delivery is separated into a checkout/review delivery checkpoint and a CI/review-workflow checkpoint. Read commit subjects with `git log --oneline origin/master..HEAD`. Existing planning work is preserved and explicitly marked historical/proposed; it is not represented as shipped functionality. The GitHub branch replaces the removed ZIP as the review artifact.

## Future branch conventions

| Pattern | Intended use | Base and boundary |
| --- | --- | --- |
| `fix/slice1-<problem>` | Authorized correction to the current payment slice | Slice 1 remote tip; retain the payment contract and update tests/evidence |
| `docs/<topic>` | Onboarding, evidence or architecture clarification | Relevant reviewed branch; no feature expansion |
| `slice/<number>-<outcome>` | Next explicitly authorized vertical slice | Latest approved implementation base; document scope and acceptance |
| `chore/paypal-sdk-v6` | Separately approved SDK migration | Approved checkout base; do not combine with payment-state redesign |

Group/AI work remains intended product direction but is paused until an explicit next-slice decision. There is no group or AI implementation branch in this delivery.

## Documentation authority

1. [README](../README.md): current setup and implemented scope.
2. [Slice 1 review](SLICE1_REVIEW.md): state model, tests, evidence provenance and known limitations.
3. [Storage decision](STORAGE_HOSTING.md): local/hosted persistence requirements.
4. [Development guide](DEVELOPMENT_GUIDE.md), [CONTRIBUTING](../CONTRIBUTING.md), [AGENTS](../AGENTS.md): integration and collaboration practices.
5. [Phase 0](WORKSHOP_PHASE0_REVIEW.md): original workshop proposal; corrections and implemented scope are in the Slice 1 review.
6. [Earlier retail guide](history/RETAIL_DEVELOPMENT_GUIDE.md), [product ideas](PRODUCT_DIRECTION.md), [video feasibility](FEASIBILITY.md): historical context, not current implementation or future-work authorization.

When scope/status changes, update this map and the README in the same change. Keep a reviewed slice's evidence intact rather than relabeling every green test run as acceptance.
