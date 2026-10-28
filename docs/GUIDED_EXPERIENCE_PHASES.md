# Common Ground: phased experience delivery

28 October 2026. Implementation base: `dev/aarya` at `4fabe98`, fetched and fast-forwarded into the clean local Slice 3 branch. This extends the collaborators' feature-package refactor. New work is local and uncommitted.

The product journey is discover, invite, confirm privately, compare together, review exact shares, approve independently, then open a private ticket. The reference URL could not be loaded by the web reader or public HTTP fetch. Its appearance has not been inspected or copied. This implementation develops the existing GroupPay identity and addresses reproduced usability problems.

## Phase 1: one clear planning journey — implemented

- Separate My preferences and Compare our plans stages inside the existing room. Comparison opens after the participant's explicit confirmation; returning to preferences remains possible. Editing cannot confirm preferences or reserve anything.
- The existing room endpoint supplies caller-specific journey guidance from saved membership, confirmation and booking state. A confirmed participant sees that the group is waiting for others; an unconfirmed participant sees their own required action.
- The Common Ground brief shows actual confirmation counts, last checked matches and whether rules or local AI supplied the comparison. It shows no invented consensus or satisfaction percentage.
- A discovery choice remains a caller-local starting point when opening a group. It is highlighted only if the server returns it as a verified match. This is not a persisted group vote or supplier reservation.
- Peer preference edits and roster changes invalidate old comparisons, quotes and rescue proposals on refresh. An opaque revision derives from update metadata, not exposed peer limits. Server quote/freeze and post-inference checks remain authoritative between refreshes.

## Phase 2: connected discovery and runtime repair — implemented

- The authenticated catalog response includes checked availability for 2, 3 and 4 people, including cinema adjacency. Past offers remain in the payload for restoring existing reservations, but cannot be planned from discovery. Availability is a snapshot and reserves nothing.
- Discovery explains a genuinely expired catalog separately from search or budget filters, disables cards without room for the selected group size, and labels fixed-group versus per-person pricing. The create-group selector excludes past and unavailable sessions.
- Corrected a refactor regression: model assets are resolved from the application's existing `instance/ai-models`, rather than `app/recommendations/instance`. Model setup now uses `python -m app.recommendations.assets prepare --model bge`.
- Added `python -m app prepare-demo`, an explicit development-only command. It requires revision 5 and appends dated fictional sessions with new resources, using the original fictional catalog templates. Repeating it is idempotent for those dates and never releases existing holds or changes original records. It does not migrate, reset, contact PayPal or run during HTTP requests.

## Phase 3: visual and real-user acceptance — pending

1. Render desktop and narrow mobile layouts; verify stage focus, visible status, contrast, reduced motion and no horizontal clipping.
2. Ask a new tester to create/join using separate browser profiles, confirm different tastes, compare, inspect a blocked plan and explicitly preview/confirm a tradeoff without developer guidance.
3. Complete an actual multi-buyer Sandbox run separately, including reload and unresolved recovery. Record genuine provider evidence privately. Mock success does not establish settlement.
4. Collect human judgments on recommendation usefulness before making quality or fairness claims. Existing synthetic evaluation is diagnostic, not acceptance.

Computer-use initialization currently fails with `windows sandbox failed: helper_unknown_error: setup refresh had errors`. Real browser rendering has not been verified. The actual jsdom controllers and local HTTP/model flow are tested separately.

## Safe local review

From `ppl-hxn`, use the parent virtual environment:

```powershell
..\.venv\Scripts\python.exe -B -m app serve
```

Open http://localhost:8000 and hard refresh. The saved application database has not been changed in this implementation. Its old catalog may have no upcoming dates. Automatic approval review rejected running `prepare-demo` on that database because preservation instructions require explicit permission for the write. The command is implemented and tested, but applying it to the active database is pending user approval.

An isolated planning preview uses `tests/serve_ai_ui_fixture.py` at http://127.0.0.1:8021 with temporary storage, actual local BGE and a payment adapter that forbids financial calls. It never loads the user's .env and is unsuitable for testing live payments. Its data disappears when the fixture is stopped.

## Evidence

- 197 Python tests passed in 53.502 seconds on this workspace, using temporary SQLite and fake providers/models for unit contracts.
- New authenticated HTTP regression follows invite, join, independent preference confirmation, semantic comparison, exact quote, hold, individual fake approvals/authorizations, final capture and distinct private tickets. Tickets remain inaccessible before final capture and to outsiders.
- New catalog tests cover past dates, adjacency, invalid domains, original-record preservation, idempotent fresh-session creation, retained holds and production CLI refusal.
- Frontend contracts and 12 isolated demo checks passed using mocked DOM/HTTP/payment adapters. The unused browser worker was removed after audit.
- Actual DOM + live temporary API + real BGE passed staged navigation, retained discovery intent, truthful comparison brief, taste onboarding, failure/retry, blocked shares, explicit rescue confirmation, category switching, peer-edit and roster invalidation. This does not render a browser or contact PayPal.
- HTML nesting and all 213 unique IDs verified. No dependency, applied migration, credential, real financial-state, archive or outer repository change was made.
- Main-app HTTP checks verified exact updated source and no-store headers. Read-only table fingerprints matched before/after startup and live use for all tables except participant-session metadata. Saved groups, preferences, original catalog/inventory, payments and tickets were unchanged; a browser session was initialized during live use. The blocked catalog preparation was not retried.

No new commit, push, merge or deployment is included. Hosted PostgreSQL and real multi-buyer payment acceptance remain separate release work.
