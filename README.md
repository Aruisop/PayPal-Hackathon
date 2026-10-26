# GroupPay: guided collaborative booking UI

Built on Panchadip-128's `slice/3-collaborative-booking-and-equal-payments` at `41ec3d7`. The latest user-authorized redesign gives his collaborative booking a light workspace, illustrated discovery, guided steps, private planning, shared conversation, adjacent-place selection and individual approval. Workshops and the isolated solo lab remain. This is a UI-first review candidate for `Aruisop/PayPal-Hackathon` on `dev/aarya`, not an accepted release. It includes earlier Slice 3/backend integration repairs; the complete change is not frontend-only. The subsequent recommendation candidate now has real server-local CPU inference and synthetic quality/latency evidence. Browser rendering, the separate on-device worker, live payments and human-rated group quality remain unverified.

Read [Aarya_changes.md](Aarya_changes.md) for changes and evidence, [the showcase guide](HACKATHON_SHOWCASE.md) for a walkthrough, and [the original product proposal](docs/COLLABORATIVE_BOOKING_PRD.md) for context.

## Run on this workspace

The existing virtual environment is in the parent folder. From `ppl-hxn`:

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -B -m app migrate
..\.venv\Scripts\python.exe -B -m app serve
```

Open **http://localhost:8000** and use **Ctrl+F5** after an update. Preserve the existing `.env`. For a fresh clone, create a virtual environment, copy `.env.example` only when `.env` does not exist, and install the pinned requirements.

Configure `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` from the intended Business Sandbox app. Buyer credentials belong only in PayPal's approval window. The fictional suppliers use that app's one Sandbox merchant; `PAYPAL_MERCHANT_ID`, if set, validates the expected seller rather than routing money.

**Gemini is optional.** Without `GEMINI_API_KEY`, the local helper extracts editable preferences and matches the trusted catalog. With a key, `GEMINI_MODEL` defaults to `gemini-2.5-flash`; model failure is disclosed as local fallback. Neither mode can confirm preferences, authorize payments or set prices for the user.

## New: verified group recommendations with a local model

No Gemini key or hosted inference service is needed. The app uses a small CPU embedding model, prepared once on the server:

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
..\.venv\Scripts\python.exe -B model_assets.py prepare --model bge
..\.venv\Scripts\python.exe -B -m app serve
```

On this workspace the optional packages and checked model assets are already prepared; restart the server after upgrading code or repairing assets. Do not change your existing `.env` or reset a database. A missing model leaves verified rules-based matching available.

In a saved group, every member reviews and confirms their budget/time fields plus optional **What would make it your kind of experience?** likes. Click **Compare AI suggestions**. If no tastes are confirmed, use **Add or review my likes**, enter a short description, then **Confirm preferences & compare AI**; that confirmation continues the comparison automatically. The default, explicitly requested by the user, minimizes the worst modeled compromise; the selector also offers average fit and a neutral comparison in schedule order. Disagreement is labeled as a tradeoff to discuss. Rankings never select, reserve or pay automatically.

**No eligible plan to compare yet** means the hard constraints filtered out this category before AI runs. The cards show each plan, your exact share, its time in your confirmed timezone, your own blockers and whether another member also needs to review. Use **Review my budget & availability**, **Find changes I can make**, or explicitly check the other category. A tradeoff preview is unsaved; your confirmation continues the comparison. A peer-only blocker requires that member's decision. For example, a two-person $100 excursion costs $50 each; a confirmed $20 ceiling cannot cover it. These prices are USD. No API key or retry can change that constraint.

The server verifies all hard constraints before embedding confirmed taste tags. It computes each member's opportunity loss relative to their own best eligible option, then minimizes the descending loss vector lexicographically. It rereads roster, preferences and inventory after inference and rejects stale responses. Model requests neither download assets nor call an inference provider; private query vectors are not cached or returned.

Real CPU tests compare keyword, MiniLM and BGE, with raw synthetic cases/results in [evaluation](evaluation/RESULTS.md). BGE with its documented instruction ranked a relevant item first in 16/16 answerable cases, but these labels are assistant-authored, not human-reviewed, and used in model selection. The exclusion guard declines five answerable cases; semantic retrieval did not reject unrelated requests. Group regret did not improve worst labeled regret over average fit in eight diagnostic groups. Do not describe these results as production accuracy or superiority over competitors.

See [the algorithm and requirements](docs/RECOMMENDATION_DESIGN.md) and [the walkthrough](HACKATHON_SHOWCASE.md). This algorithm combines established ideas for this application; it is not claimed as a new mathematical fairness result.

## Separate optional browser AI: execution still unverified

On **Discover**, click **Enable on-device AI**, wait for the ready message, then describe a vibe such as "a peaceful outdoor adventure". Vibe Scout uses actual MiniLM sentence embeddings in a browser worker to rank the trusted catalog by meaning. It does not generate inventory, quotes, agreement scores or payment decisions. Budget and group-size controls provide discovery previews; the room checks actual confirmed constraints and availability.

AI is opt-in. First use downloads a pinned ~23 MB quantized model plus the Transformers.js/WebAssembly runtime from Hugging Face/jsDelivr. Inference runs on the device; query text is not sent to an inference service. The browser may cache model assets; the bounded embedding cache lives only in worker memory and is cleared when AI is turned off. This is semantic retrieval, not a generative chatbot. Network/model failures are disclosed as keyword search, not relabeled as AI. First-use model execution still needs a real browser smoke test on the demo machine.

**Plan Rescue** in a saved group calculates which explicit edits to *your own* confirmed budget/dates/times could unlock a real option with every other confirmed member unchanged. It checks exact cent shares, timezone, future schedules, capacity and adjacency using the existing matcher. It never changes another member's limits. **Preview changes in my fields** is an unsaved draft; review it and click **Yes, these are my preferences** to save. After AI is enabled, **Rank options with my AI vibe** orders only these verified proposals by semantic similarity. The what-if calculations are deterministic rules, clearly labeled separately from AI.

The pinned runtime/model attribution, module boundaries and verification limits are in [docs/AI_AND_GUIDED_UX.md](docs/AI_AND_GUIDED_UX.md).

## Try it alone first

Click **Walk me through** for the four-step explanation, then open **Solo demo lab**. Cinema, a fixed-price excursion and Chaos use isolated browser memory. Switch fictional Alice/Bob/Charlie or use the three-person teaching view. Confirm each budget, reserve local places, approve simulated shares and step through captures. The $100 example splits into $33.34 + $33.33 + $33.33.

Chaos leaves refunds and voids pending until each simulated recovery completes. Readiness uses an example amount you enter. Its local admission ledger rejects invalid and reused `SIM-` references. No lab action contacts the backend, changes session identity, reserves saved inventory or produces an application ticket. Reset/reload clears only the lab.

## Try the saved group workflow

1. Create a group and copy its invite. Each real member joins in a different browser profile or device; ordinary tabs share one identity.
2. Save your display name and privacy choice. Enter preferences in your private concierge, review/edit the actual extracted fields, then confirm. Blank fields mean flexible. All times are shown in the browser's timezone.
3. Use the separate saved group conversation to discuss a plan. Each member confirms independently. Readiness counts and next actions update every five seconds; private budgets and payment references stay private.
4. Find group matches. Conflicts remain visible; there is no invented agreement score or automatic first-offer fallback. The organizer reviews adjacent seats or excursion places, requests an exact server quote and holds the selection for 15 minutes.
5. Each member reviews their exact share and terms, checks consent, and approves their own Sandbox order in the actual PayPal window. Server authorization runs only after buyer approval. A hold does not issue a ticket.
6. After every authorization is verified, the organizer completes capture. Captures are sequential. Only validated completed captures for the whole frozen roster unlock each member's own fictional ticket and real QR encoding.
7. If an outcome is unknown or pending, recheck the saved approval or reconcile group recovery. Do not reset storage or create a replacement payment. Pending refunds/voids remain unresolved until confirmed.

The ticket checker compares only the current owner's confirmed ticket. It does not redeem real admission, validate a supplier signature or integrate with Apple/Google Wallet. Cookie identity has no account recovery; clearing it loses access to that identity.

## Merchant checkout demo: Pay together with PayPal

On a fictional catalog card, **Pay together with PayPal** opens a focused merchant checkout before any PayPal approval popup. A buyer can either pay alone or create a fixed 2–4 payer checkout, share its invite, then hold the merchant order after the intended roster joins. The server owns the catalog item, total, currency, payer count, selected inventory and exact-cent equal split. Each payer independently accepts and authorizes only their own amount through the ordinary PayPal popup. The order confirmation appears only after every capture is validated as completed.

This is an in-app merchant demonstration, not a public merchant SDK, hosted PayPal-window customization, webhook integration, or multi-merchant marketplace. The control is merchant UI placed before PayPal's controlled approval window. Unequal splits and AI allocation are not implemented: a future assistant may only propose an allocation that the server validates against the frozen total and each affected payer explicitly accepts.

See [the group-payment platform direction](docs/GROUP_PAYMENT_PLATFORM_DIRECTION.md) for the delivered merchant-demo boundary and the requirements for a future merchant integration.

## Storage and recovery

SQLite is local development storage. `.env` selects the active database; the restored original used a separate revision 3 file. Revisions 4 and 5 add durable payment operations/workflows and shared room messages; revision 6 additively records merchant-checkout mode, its trusted offer and fixed intended payer count. Applied revisions are never rewritten. Existing legacy purchases, IDs and tickets are preserved but require merchant review because their original synthetic or unvalidated state cannot establish payment.

The previous revision 5 application database remains separate. Do not mix or downgrade these databases. Hosted operation requires managed PostgreSQL, HTTPS and secure cookies; PostgreSQL runtime/concurrency is still unverified.

An authorized operator can run a bounded recovery pass:

```powershell
..\.venv\Scripts\python.exe -B -m app recover
```

This can query and mutate saved Sandbox recovery operations. GET polling performs no provider mutation. Repeated automatic progress needs an explicitly arranged operator schedule; there is no hidden worker.

## Validate

```powershell
..\.venv\Scripts\python.exe -B -m unittest discover -s tests
..\.venv\Scripts\python.exe -m pip check
node tests/test_frontend_contract.cjs
node tests/test_demo_contract.cjs
node tests/test_ai_contract.cjs
git diff --check
```

The full 190 Python tests pass with mocked providers, including seven Plan Rescue cases and five additional no-match diagnosis regressions. Frontend contracts execute discovery, walkthrough, actual room callbacks, an unsaved rescue preview, explicit confirmation and the payment flow using mocked DOM/HTTP/SDK. AI contracts exercise loading/retry, catalog-only ranking validation and the actual worker handler with mocked embeddings. The isolated demo has 12 contract checks. Those contract tests use mocks. Separately, the native CPU benchmark executes actual model weights and the recommendation route on temporary synthetic groups. A jsdom/live temporary API test uses real BGE inference and checks taste onboarding, no-match diagnostics, explicit tradeoff confirmation, peer limits and roster invalidation; it does not render a browser. Browser tooling currently fails during initialization; desktop/mobile, browser-worker inference, real multi-buyer Sandbox checkout, Gemini and PostgreSQL verification remain outstanding.

The UI snapshot fb07b49 was published to [Aruisop/PayPal-Hackathon, dev/aarya](https://github.com/Aruisop/PayPal-Hackathon/tree/dev/aarya). This checkpoint extends it with the user-authorized local AI recommendation and no-match usability changes; see Aarya_changes.md for scope and evidence. Publication does not imply acceptance, merge or deployment. License selection and submission requirements still need team review.
