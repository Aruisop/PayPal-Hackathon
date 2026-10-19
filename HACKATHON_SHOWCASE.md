# Try the new GroupPay experience

Open http://localhost:8000 and press **Ctrl+F5**. The app keeps your existing database and browser identity. No Gemini key is needed.

## One-person rehearsal, no payments

1. Click **Walk me through** in the header. Read the four steps with Next/Back or the dots. This explains who acts and when money is only held versus captured.
2. On **Discover**, inspect actual movie/adventure cards. Change People and budget to see discovery previews. A $100 adventure for three previews $33.34 + $33.33 + $33.33; the saved room later checks the real roster and availability.
3. Click **Enable on-device AI**. First use needs internet for the pinned ~23 MB model plus runtime. Wait for **AI ready**, describe "an immersive science fiction night" or "a peaceful outdoor escape", then click **Find my vibe**. The labeled AI ranks actual catalog IDs by meaning. If assets cannot load, the screen says keyword search. Turning AI off terminates its worker.
4. Open **Solo demo lab**, choose Cinema, The $100 adventure or What if a payment fails. Use the three-person teaching view or switch fictional Alice/Bob/Charlie. Confirm budgets, choose adjacent places, hold, approve each simulated share and advance sequential captures.
5. In the failure scenario, observe retained places and pending refunds/voids, then finish each simulated recovery item. The entered readiness amount is hypothetical. SIM tickets use only the local model ledger and duplicate-admission check.

The lab stays in isolated memory, makes no backend/payment requests, does not change identities, and cannot reserve saved inventory. Reset/reload clears only that rehearsal. The AI search is real inference only after its ready message and a successful ranking; automated AI tests use mocked embeddings and do not prove it ran on your device.

## Actual local-model group suggestions

The optional CPU dependencies and BGE assets are prepared on this machine; after a code update restart the server, then Ctrl+F5. For a clean setup follow README's requirements-ai installation and `model_assets.py prepare --model bge` commands. No Gemini key is needed for this feature.

If the result is **No eligible plan to compare yet**, read each blocked card before changing anything. The $100/$120 excursions cost $50/$60 each for two people. Your own blockers are identified privately; a peer blocker requires that person's review. **Find changes I can make** previews only verified own-preference edits. Confirm a preview only if it reflects your actual limits; this continues the comparison. **Check cinema nights instead** checks that category without changing preferences. No model key or AI retry overrides a confirmed budget.

1. Use two separate browser profiles, join one saved group, and confirm flexible dates/times and adequate budgets independently.
2. In each private review, enter positive descriptive likes in **What would make it your kind of experience?** For example one member likes science fiction, another likes acoustic drama. Explicitly confirm the fields. Blank likes are flexible and do not invent a ranking vote.
3. Click **Compare AI suggestions**. If prompted, choose **Add or review my likes**, then explicitly **Confirm preferences & compare AI** to continue. The default minimizes the worst modeled compromise. Note the actual local model, number of members with tastes and measured server elapsed time. No action auto-selects or reserves a plan.
4. Compare **Highest average modeled fit** and **Show both views**. A different ranking is a visible policy tradeoff, not evidence that one predicts happiness. When semantic favorites disagree, the screen says to discuss the tradeoff.
5. Try a hard budget conflict: the model cannot bring an ineligible offer back. A single eligible option skips inference; missing tastes/model assets give an honest non-AI result. Negative/requirement-like tastes trigger clarification rather than pretending semantic similarity enforces them.
6. Choose an eligible plan, review the exact quote and continue the existing individually approved Sandbox flow only when ready. Do not reset unresolved purchases.

For solo real-inference evidence, run `python evaluation/benchmark_recommendations.py --model all --http` against temporary synthetic groups. This is not the isolated payment lab and is not a rendered-browser test. Read the failure cases in evaluation/RESULTS.md before recording. Do not present raw 16/16 retrieval as deployed workflow accuracy; the guard abstains on five answerable cases and unrelated requests remain unsupported.

## Saved group and Plan Rescue, two browser profiles

1. Start a group from Discover. Copy its invite into a separate browser profile or another device. Ordinary tabs share one identity. Keep both windows open. Save each display name and sharing choice if desired.
2. In the first profile, enter "Any day and time, budget under $1" in **Your planning space**. Review the structured fields and explicitly confirm. In the second profile, confirm flexible days/times and a $50 per-person budget. Blank schedule fields mean flexible; do not choose a weekday accidentally inconsistent with the fixed catalog.
3. Return to the first profile and click **Find our common ground**. The $1 ceiling should block the current movie catalog. The conflict is an actual result, not a scripted AI response.
4. Click **Explore my tradeoffs**. Plan Rescue shows real options plus the exact changes to your own ceiling/dates/times that would make each fit while leaving the other member's constraints untouched. If AI was enabled, **Rank options with my AI vibe** orders these verified proposals by your own description. Another member's private limits are never displayed.
5. Click **Preview changes in my fields**. Point out the unsaved draft and disabled group matching. Nothing is saved yet. Review the edit, then click **Yes, these are my preferences**. This is explicit consent to a preference change, not financial consent.
6. The organizer reviews a compatible movie, adjacent seats, and **Review everyone's exact share**. Hold those places for 15 minutes. Explain the next-action panel and the newly visible approval card.
7. Each browser participant must check consent and approve their own actual PayPal Sandbox order. Use the intended Sandbox app/merchant and appropriate buyer login in each approval window. Local aliases or fictional lab personas are not PayPal accounts. Keep the credentials already configured; do not reset a database to fix an unresolved payment.
8. After all required authorizations are verified, the organizer clicks **Complete group capture**. Only verified completed captures for the entire frozen roster unlock each owner's private fictional ticket and actual QR.
9. Reload the group to check persistence. If an outcome is unknown/pending, use **Recheck my saved approval** or organizer **Reconcile group recovery**. A reservation/approval is not a ticket, and an attempted refund is not completed recovery.

If you only have one application identity or cannot approve actual buyer orders, use the solo lab for the payment rehearsal. Do not use aliases to pretend independent buyer authorization occurred.

## Before recording a submission

Browser automation is unavailable in this environment. Verify real desktop/mobile rendering, first-use model inference and failure fallback, keyboard dialogs, SDK approval windows, two-profile identity isolation and actual multi-buyer Sandbox evidence on the demo machine. Automated tests use fake payment providers and embeddings. Do not claim they establish real settlement, model quality, venue admission, wallet integration or PostgreSQL hosting.

Show the useful novelty clearly: a private on-device semantic scout plus transparent, verified own-preference tradeoffs, followed by independent payment approval. Keep the deterministic checks distinct from AI. The existing guardrail inspector remains an interpretation-only actual response, not a universal security guarantee. Never expose credentials, cookies or private capture references in public recordings.
