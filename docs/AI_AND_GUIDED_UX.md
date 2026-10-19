# Current server-local recommendation extension

A subsequent user-authorized candidate adds actual CPU embeddings and constraint-first semantic regret/average comparisons for confirmed group tastes. This is separate from the browser-worker feature below. See [RECOMMENDATION_DESIGN.md](RECOMMENDATION_DESIGN.md) for the algorithm, privacy boundary, requirements and research; [the measured results](../evaluation/RESULTS.md) for actual inference, synthetic-label limits and failures. The browser-worker account below describes the earlier UI-first snapshot and still has no rendered-browser inference evidence.

# Guided planning and key-free AI

This extends Panchadip's Slice 3 collaborative booking rather than changing its financial protocol. The user explicitly requested the new presentation after the original-style integration. There is no new database migration, Python dependency, credential or payment adapter in this pass.

## What is actually AI

Vibe Scout performs semantic retrieval with `Xenova/all-MiniLM-L6-v2` using Transformers.js 3.8.1 in a module worker. Normalized mean-pooled embeddings are compared by cosine similarity. The model can connect descriptions such as "a peaceful escape" with catalog wording that does not repeat the same words. This is retrieval over existing options, not generated offers, consensus inference, sentiment analysis, financial advice or a conversational LLM.

The same model can order Plan Rescue proposals by the meaning of the current member's original private description. The server calculates proposals first; the model receives only a bounded description and trusted proposal IDs/catalog text. The client rejects missing, duplicate, invented or invalid ranked IDs/scores. No probability or agreement percentage is displayed.

The existing server-side Gemini preference interpreter remains optional. Without its key, the private form uses the explicitly labeled local parser and manual review. On-device AI does not secretly replace that parser with a chatbot.

## What is verified calculation

`rescue.py` reads the caller's membership and all confirmed constraints, then closes its read connection. For each trusted offer it calculates the caller's exact prospective cent share in actual roster order. It proposes only necessary own-budget/date/day/start-window/finish-limit edits. It substitutes that draft for the caller alone and runs the same deterministic catalog matcher used for group planning. If another member's unchanged constraint or inventory availability blocks the option, it is excluded.

Responses contain the caller's proposed constraints and edits, actual offer/share data, and a coarse result. They do not disclose another member's budget, constraints, raw text, aliases or payment references. Already-fitting options are labeled as needing no edits. Frozen purchases reject this planner. The endpoint is authenticated and CSRF protected; it writes no preference, inventory or financial state and calls no model/provider.

Clicking a proposal copies it into a visibly unsaved private draft. Group matching and reservation are disabled while that draft is edited. Only an explicit existing confirmation action saves it. A quote and freeze still revalidate actual current server state; a rescue proposal never reserves places.

## Browser responsibilities

| Module | Responsibility |
| --- | --- |
| `public/ai-worker.mjs` | Pinned runtime/model load; serialized bounded inference; worker-memory embedding cache |
| `public/ai.js` | Explicit enable/disable, progress, timeout/retry, RPC validation and honest keyword fallback utility |
| `public/discovery.js` | Actual catalog cards and filters, safe text rendering, AI/basic search labels, exact excursion preview shares |
| `public/guide.js` | Four-step walkthrough with previous/next/dots and focus return |
| `public/room.js` | Actual saved flow, phase explanations, private draft preview/confirmation, verified proposal ranking |
| `rescue.py` | Read-only deterministic counterfactual generation and eligibility checks |

AI is lazy and opt-in. The ~22,972,370-byte quantized model plus runtime/tokenizer assets are downloaded only after enabling. Model assets may remain in the browser's normal cache; search embeddings are bounded to 64 worker-memory entries and disappear when the worker terminates. User query text is not sent to a hosted inference endpoint. Hugging Face/jsDelivr necessarily receive ordinary asset download requests. This is not a fully offline first visit, a certified privacy audit or a formal sandbox boundary against a compromised third-party runtime.

The model revision is `da5f6eac91a9596269707e15ec694e50e25a0d14`; dependency versions are explicit. Their original licenses apply: see [Transformers.js source/license](https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1/LICENSE) and the [model card](https://huggingface.co/Xenova/all-MiniLM-L6-v2). The application still needs its own team-selected license. Implementation follows the official [vanilla JS/worker guidance](https://huggingface.co/docs/transformers.js/v3.8.1/en/tutorials/vanilla-js) and [feature-extraction API](https://huggingface.co/docs/transformers.js/api/pipelines).

## Interaction and visual design

The desktop has a navy rail and light content workspace. Mobile uses bottom navigation and stacked panels. Discovery has code-native illustrations, budget/group-size previews and a clear create/join path. The group room explains Gather / Agree / Approve / Go, gives a concrete next action, and introduces payment controls only after a saved reservation. Private input, shared chat, financial consent and the ticket remain separate. Recovery details automatically expand when recovery is required.

The walkthrough explains authorization versus capture, separate browser identities, preference consent and the fictional-ticket limit. Sounds start muted. Controls retain visible focus states, status announcements, reduced-motion support, keyboard dialog handling and text-rendered user input. Design references include [W3C clear steps](https://www.w3.org/WAI/WCAG2/supplemental/patterns/o1p04-clear-steps/) and [multi-page form guidance](https://www.w3.org/WAI/tutorials/forms/multi-page/); no WCAG conformance is claimed.

## Evidence and remaining validation

The full 132-test Python suite passes, including seven rescue tests covering exact own-budget edits, peer privacy, timezone-specific edits, the excursion remainder, membership/confirmation/frozen boundaries, unavailable/past offers and HTTP identity/CSRF. Existing financial tests use mocked PayPal. Frontend contracts execute the real scripts with mocked DOM/HTTP/SDK, including walkthrough, catalog filtering, unsaved rescue preview, confirmation and payment/ticket callbacks. AI contracts run loading/retry/disable and the actual worker handler with mocked embeddings. Twelve isolated lab contracts pass.

The exact pinned runtime, model config and quantized model URLs returned HTTP 200. That proves asset availability, not inference compatibility. Computer-use tooling fails before browser launch with kernel-assets error 3. Actual model inference, visual desktop/mobile layout, keyboard/popup behavior, real multi-buyer Sandbox checkout, Gemini and PostgreSQL runtime remain unverified. Do not represent mocked embeddings as a real-model quality evaluation.

Before the hackathon, load AI on the actual demo browser/network and try at least a sci-fi phrase, an outdoor phrase and an unrelated phrase. Check meaningful ordering, honest fallback when the network is blocked, and responsiveness. Inspect 1440px desktop and 390px mobile layouts, keyboard-only dialogs, two-profile planning, and independently buyer-approved Sandbox capture. Record real observations separately from automated evidence.
