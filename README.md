# GroupPay: guided collaborative booking UI

Built on Panchadip-128's `slice/3-collaborative-booking-and-equal-payments` at `41ec3d7`. The latest user-authorized redesign gives his collaborative booking a light workspace, illustrated discovery, guided steps, private planning, shared conversation, adjacent-place selection and individual approval. Workshops and the isolated solo lab remain. This is a UI-first review candidate for `Aruisop/PayPal-Hackathon` on `dev/aarya`, not an accepted release. It includes earlier Slice 3/backend integration repairs; the complete change is not frontend-only. AI integration code is present, but actual model execution remains unverified.

Read [Aarya_changes.md](Aarya_changes.md) for changes and evidence, [the showcase guide](HACKATHON_SHOWCASE.md) for a walkthrough, and [the original product proposal](docs/COLLABORATIVE_BOOKING_PRD.md) for context.

## Run on this workspace

The existing virtual environment is in the parent folder. From `ppl-hxn`:

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -B server.py migrate
..\.venv\Scripts\python.exe -B server.py serve
```

Open **http://localhost:8000** and use **Ctrl+F5** after an update. Preserve the existing `.env`. For a fresh clone, create a virtual environment, copy `.env.example` only when `.env` does not exist, and install the pinned requirements.

Configure `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` from the intended Business Sandbox app. Buyer credentials belong only in PayPal's approval window. The fictional suppliers use that app's one Sandbox merchant; `PAYPAL_MERCHANT_ID`, if set, validates the expected seller rather than routing money.

**Gemini is optional.** Without `GEMINI_API_KEY`, the local helper extracts editable preferences and matches the trusted catalog. With a key, `GEMINI_MODEL` defaults to `gemini-2.5-flash`; model failure is disclosed as local fallback. Neither mode can confirm preferences, authorize payments or set prices for the user.

## Optional AI integration: execution unverified

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

## Storage and recovery

SQLite is local development storage. `.env` selects the active database; the restored original used a separate revision 3 file. Revisions 4 and 5 add durable payment operations/workflows and shared room messages without rewriting applied revisions. Existing legacy purchases, IDs and tickets are preserved but require merchant review because their original synthetic or unvalidated state cannot establish payment.

The previous revision 5 application database remains separate. Do not mix or downgrade these databases. Hosted operation requires managed PostgreSQL, HTTPS and secure cookies; PostgreSQL runtime/concurrency is still unverified.

An authorized operator can run a bounded recovery pass:

```powershell
..\.venv\Scripts\python.exe -B server.py recover
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

The full 132 Python tests pass with mocked providers, including seven new Plan Rescue cases. Frontend contracts execute discovery, walkthrough, actual room callbacks, an unsaved rescue preview, explicit confirmation and the payment flow using mocked DOM/HTTP/SDK. AI contracts exercise loading/retry, catalog-only ranking validation and the actual worker handler with mocked embeddings. The isolated demo has 12 contract checks. These are not rendered-browser, real-model or live-payment results. Browser tooling currently fails during initialization; desktop/mobile, actual model inference, real multi-buyer Sandbox checkout, Gemini and PostgreSQL verification remain outstanding.

This snapshot is prepared for publication to [Aruisop/PayPal-Hackathon, dev/aarya](https://github.com/Aruisop/PayPal-Hackathon/tree/dev/aarya). Publication does not imply acceptance, merge or deployment. License selection and submission requirements still need team review.
