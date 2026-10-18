# Slice 3 integration development guide

Start with the README, Aarya_changes.md, AGENTS.md and current Slice 3 review. Base is Panchadip's commit 41ec3d7. The user authorized repairing the original experience, then explicitly requested a guided UI redesign and key-free AI; historical Slice 1/2 proposals do not override the implemented code.

| Path | Responsibility |
| --- | --- |
| public/app.js | Navigation, create/join dialogs, sounds, architecture guide, lab entry and individual workshop CAPTURE checkout |
| public/room.js | Session-owned group room, private preference review, shared messages, progress, resource selection, quote, real AUTHORIZE SDK callbacks, explicit recovery and private ticket UI |
| public/discovery.js, public/guide.js | Illustrated trusted catalog, filters, optional semantic search and four-step walkthrough |
| public/ai.js, public/ai-worker.mjs | Lazy on-device MiniLM embeddings; bounded catalog-only rankings, no preference inference service |
| recommendations.py | Confirmed hard eligibility, local semantic comparison, user-selected objective and post-inference stale rejection |
| semantic.py, model_assets.py | Optional CPU-only local embeddings, catalog cache, explicit verified public-asset preparation |
| benchmark_recommendations.py, evaluation/ | Frozen synthetic fixtures, actual inference/route timing and honest reproducible metrics |
| rescue.py | Read-only own-preference counterfactuals rechecked by the authoritative matcher; never auto-confirms |
| public/demo.js | Independent in-memory fictional three-person model, readiness, sequential capture, pending compensation, local tickets and duplicate admission rejection |
| server.py | Session/Origin/CSRF/ownership HTTP boundary, explicit migration and recovery commands, static routes and interpretation-only inspector |
| storage.py | SQLAlchemy Core schema and immutable migration sequence, trusted catalog, participant identities |
| groups.py, room.py | Membership/invites/privacy and persisted member-authored messages/coarse coordination |
| ai_planner.py, planning.py | Validated untrusted interpretation, useful no-key fallback, confirmation, authoritative matching/selection checks |
| collab_booking.py | Quotes, exact shares, serialized reservations, consent and private views |
| booking_payments.py | Persisted operation identities, reconciliation, capture and compensation |
| booking_lease.py, payment_evidence.py, booking_errors.py | Exclusive operation leases/fenced writes, pure provider evidence validation, domain errors |
| payments.py | Sandbox adapter; no browser credentials or database authority |
| checkout.py | Preserved individual workshop coordinator, owner recovery and protected lesson entitlement |
| ticketing.py | Actual QR encoding of an existing owned ticket; no issuance or real admission authority |
| tests/ | Mock provider regressions, original UI/SDK contracts and independent local-demo model checks |

Keep price, currency, roster, merchant validation and inventory server-owned. Confirm every member's own preferences before matching. Only all required validated completed captures unlock private tickets. Persist request IDs and known provider IDs; reconcile unknown outcomes before retrying. Never hold a transaction over a provider call. Fence writes and keep failed refunds/voids visible. GET polling is read-only.

Migrations 4 and 5 extend revision 3 without rewriting original schemas. Legacy purchase evidence is preserved and quarantined for merchant review. Never reset storage or substitute the prior application's database. Local SQLite is not hosting; managed PostgreSQL runtime/concurrency still needs verification.

The real room uses one participant per browser profile. Aliases cannot switch identity. Shared discussion is distinct from private preferences, and explicit sharing consent governs aliases/coarse progress. Cookie identities have no account recovery.

The lab receives copied catalog DTOs and has no network, cookie, session or persistent-storage capability. Its reset affects only its model. Tests of the model do not establish provider settlement. The application ticket checker verifies only the current owner's confirmed reference and does not redeem supplier admission.

Read [AI and guided UX](AI_AND_GUIDED_UX.md). Run unittest, frontend, AI and demo contracts, dependency checking after dependency edits, and git diff --check. Record actual browser, real Sandbox, Gemini and PostgreSQL evidence separately. No commit/push/deploy is implied by implementation authorization.

The subsequent AI candidate builds on fb07b49. Read [recommendation design](RECOMMENDATION_DESIGN.md) and [actual results](../evaluation/RESULTS.md). No model call belongs in polling, quotes, payment operations or a DB transaction. Preserve user-requested compromise default and explicit alternatives. Synthetic quality is not real-user satisfaction.
