# Group coordination: Slice 2 review packet

Status: implemented on `slice/2-group-coordination`, based on the user-accepted Slice 1 development branch. **Architecture review pending.** This branch adds coordination only; the individual checkout, PayPal SDK v5, payment states and lesson authorization remain the Slice 1 implementation.

## Delivered flow

An organizer creates a named group and copies its invite link. Another browser profile opens the link and joins under its own server-issued participant session. Joining the same link again returns the same membership. Only the organizer can choose one of the two trusted catalog workshops; the choice is deliberately immutable so a paid member is not silently pointed to a different workshop. Member profiles see the choice and their own booking/payment state. The group booking button selects that workshop in the existing individual checkout. Every member approves and captures their own PayPal order and receives only their own sample lesson after a validated `COMPLETED` capture.

The group API is `GET/POST /api/groups`, `POST /api/groups/join`, `GET /api/groups/<id>`, and `POST /api/groups/<id>/selection`. Invite knowledge only permits joining. Group reads require membership, selection requires organizer identity, and all mutations retain the existing session/Origin/CSRF checks. A group response includes the requester's booking only. Only the organizer receives the invite URL. Client-supplied amounts have no effect.

## Storage and migration

Revision 2 adds `workshop_groups` (ID, name, organizer participant, 256-bit random invite capability, nullable chosen workshop, creation time) and `group_memberships` (ID, group, participant, join time, unique group/participant). Group creation inserts the group and organizer membership in one transaction; concurrent repeat joins are constrained by database uniqueness. A selection uses a conditional update and cannot be replaced after one choice. Existing revision 1 payment tables are unchanged. The group view finds the current participant's existing unique booking for the chosen workshop; a prior individual purchase for that workshop is reused. A participant joining multiple groups that choose the same workshop likewise sees that one individual booking, never a second charge for group membership.

Local SQLite is persistent; hosted judges must use durable managed PostgreSQL with the same versioned migration path in [STORAGE_HOSTING.md](STORAGE_HOSTING.md). Run `python server.py migrate` before a production restart; production startup requires revision 2. No transaction spans a PayPal request. This branch does not claim an executed PostgreSQL deployment.

## Verification and evidence provenance

The focused group suite uses a stateful fake PayPal service, as do the retained Slice 1 payment tests. These are mocks, not new Sandbox transactions. The group tests cover invite isolation, safe repeat/concurrent joins, organizer-only trusted-catalog selection, separate orders and owner-only booking/lesson access for a completed buyer versus a pending buyer, persistence after restart, and migration of a populated revision 1 database. The existing payment suite remains a regression guard. `.venv\Scripts\python.exe -m unittest discover -s tests -v` passed **36 tests**. `pip check`, Python compilation, JavaScript syntax (`node --check`) and `git diff --check` passed.

A separate credential-free local HTTP walkthrough used two Flask clients, a temporary SQLite database, and fake PayPal. It observed successful invite join/shared choice, buyer lesson HTTP 200 after mocked completion, unpaid profile booking/lesson HTTP 404, and membership/denial after app restart. This exercises route behavior, not browser rendering or real Sandbox settlement. Browser invite-click timing and SDK rendering remain unverified.

One independent, read-only adversarial agent reviewed the staged code diff after deterministic checks. It traced member-gated group views, organizer selection, duplicate joins, independent checkout ownership and the invite UI, and reported **no concrete findings**; it did not edit code or reproduce a failing case. The one permitted review cycle therefore required no code revision. Model token telemetry was unavailable to both builder and reviewer, so exact token counts cannot be reported; the targeted revision phase was not needed. Proposed decision: **accept Slice 2 for architecture review**, while retaining the browser and hosted-database limitations below.

No new PayPal Sandbox purchase was initiated for Slice 2. The user-observed real Sandbox evidence for Slice 1 remains in [SLICE1_REVIEW.md](SLICE1_REVIEW.md); it does not prove the new group browser UI. OAuth success is not purchase evidence.

## Two-profile walkthrough for review

1. Preserve `.env` and `instance/workshops.db`; run the migration and start the server at the exact `APP_ORIGIN`. Use profile A and a separate profile B, not two tabs sharing cookies.
2. In A, create a group and copy the invite link. Open it in B. B should join once; opening it again should not add another member. Profile C without the invite should receive 404 for the group URL.
3. In A, choose a future workshop. B sees the same selection after its group card refreshes (or a page refresh). B cannot choose or change the workshop. A cannot switch it after choosing.
4. Both profiles use **Book or view your own payment**. Confirm each gets a different booking and PayPal order for the catalog's fixed USD price. Pay using separate Personal Sandbox buyer accounts if performing a real Sandbox walkthrough. Approval alone must stay locked; only completed capture unlocks a lesson.
5. After A completes and B remains unpaid or pending, A sees its own receipt and lesson. B sees only its own unpaid/pending state. Paste A's booking and lesson URLs into B after B has established its own session; both must return 404. B's own lesson stays 403 until B's capture is validated completed.
6. Restart without deleting the database and refresh both profiles. Group membership, choice, and each profile's own status should persist.

## Known limitations

- Browser-profile cookies are the only demo identity. Clearing or expiring one loses access to that participant's group and purchases; there is no login or recovery.
- Anyone with the invite link can join. There is no link rotation, removal, membership moderation or organizer transfer. Invite capabilities are stored in the database so the organizer can copy the same link after restart; they must be treated as sensitive operational data, though they do not authorize group reads without joining.
- Group workshop selection is one-time. There is no rescheduling or cancellation workflow. A member who joins after the selected workshop starts cannot begin a new purchase; existing paid bookings remain visible.
- Group status contains only the viewer's payment/lesson data and member count. It does not expose who has paid, pooled money, seat inventory, recommendations or AI preferences.
- Group association is computed from participant plus selected workshop. Multiple groups choosing the same workshop share that participant's one booking; there is no separate group-specific purchase. The unused Slice 1 `future_membership_id` column is left unchanged rather than altering an applied payment revision.
- No browser automation, live PostgreSQL execution or new Sandbox purchase is claimed until separately recorded. Existing unresolved PayPal attempts retain Slice 1's conservative reconciliation limits.
