# Guided planning and local group AI

The product has one semantic AI feature: server-local BGE compares confirmed group likes across verified upcoming options. Discover uses simple keyword search, and Plan Rescue uses deterministic what-if rules. There is no browser model download or hosted model call in group ranking. See [RECOMMENDATION_DESIGN.md](RECOMMENDATION_DESIGN.md) for the algorithm and privacy boundary, and [measured results](../evaluation/RESULTS.md) for real model execution and the limits of the synthetic evaluation.

This extends Panchadip's Slice 3 collaboration without changing its financial protocol. The model is optional at runtime: install the AI dependencies, prepare the pinned model explicitly, then restart the app. The no-key path still supports planning and deterministic rules-based matches.

## What is actually AI

The group comparison endpoint applies confirmed budget/date/time and inventory rules first. If at least two verified choices remain, it embeds the trusted catalog descriptions and each member's confirmed positive taste tags with local ONNX BGE-small-en-v1.5. The default order minimizes the largest modeled opportunity regret; average-fit and schedule-order views are alternatives. These are ranking proxies, not measured happiness, agreement or fairness.

There is no Gemini key requirement. The optional Gemini preference interpreter is separate; without its key, the app uses a rules parser and asks the member to review the extracted fields. AI never parses authoritative constraints, confirms preferences, chooses seats, sets prices, starts payments or issues tickets.

## What is verified calculation

`rescue.py` reads the caller's membership and all confirmed constraints, then closes its read connection. For each trusted offer it calculates the caller's exact prospective cent share in actual roster order. It proposes only necessary own-budget/date/day/start-window/finish-limit edits. It substitutes that draft for the caller alone and runs the same deterministic catalog matcher used for group planning. If another member's unchanged constraint or inventory availability blocks the option, it is excluded.

Responses contain the caller's proposed constraints and edits, actual offer/share data, and a coarse result. They do not disclose another member's budget, constraints, raw text, aliases or payment references. Already-fitting options are labeled as needing no edits. Frozen purchases reject this planner. The endpoint is authenticated and CSRF protected; it writes no preference, inventory or financial state and calls no model/provider.

Clicking a proposal copies it into a visibly unsaved private draft. Group matching and reservation are disabled while that draft is edited. Only an explicit existing confirmation action saves it. A quote and freeze still revalidate actual current server state; a rescue proposal never reserves places.

## Current responsibilities

| Module | Responsibility |
| --- | --- |
| `public/discovery.js` | Catalog cards, keyword search, availability and price previews |
| `public/guide.js` | Four-step walkthrough with previous/next/dots and focus return |
| `public/room.js` | Saved group flow, server-derived availability status, comparison, private draft preview/confirmation and booking callbacks |
| `rescue.py` | Read-only deterministic counterfactual generation and eligibility checks |
| `semantic.py` | Pinned local ONNX model loading, pooling, finite-vector checks and trusted catalog-vector cache |

Model weights are prepared by an explicit operator command into the ignored application instance directory. Requests do not download assets or call an inference provider. The encoder caches only trusted catalog vectors; member text and query vectors are not cached by the encoder or returned to peers. Inference is serialized, runs without an open database connection, and the service rereads the roster/preferences/catalog afterward to reject stale results. This is a server privacy boundary, not differential privacy or protection from a compromised app host.

## Interaction and visual design

The desktop has a navy rail and light content workspace. Mobile uses bottom navigation and stacked panels. Discovery has code-native illustrations, budget/group-size previews and a clear create/join path. The group room explains Gather / Agree / Approve / Go, gives a concrete next action, and introduces payment controls only after a saved reservation. Private input, shared chat, financial consent and the ticket remain separate. Recovery details automatically expand when recovery is required.

The walkthrough explains authorization versus capture, separate browser identities, preference consent and the fictional-ticket limit. Sounds start muted. Controls retain visible focus states, status announcements, reduced-motion support, keyboard dialog handling and text-rendered user input. Design references include [W3C clear steps](https://www.w3.org/WAI/WCAG2/supplemental/patterns/o1p04-clear-steps/) and [multi-page form guidance](https://www.w3.org/WAI/tutorials/forms/multi-page/); no WCAG conformance is claimed.

## Evidence and remaining validation

The current 197-test Python suite passes using mocked payment providers and model unit doubles. The frontend contract uses mocked DOM/HTTP/SDK; the solo lab has 12 isolated behavior checks. Separately, actual BGE inference was run locally and the authenticated recommendation route passed against temporary SQLite with real model weights. These checks do not render a browser or establish human preference quality. A visual browser attempt failed during computer-use initialization, and genuine multi-buyer Sandbox payment and PostgreSQL runtime remain unverified.

The evaluation set contains five offers and assistant-authored relevance labels used during model selection; it is diagnostic only. Main product limitations are the narrow fictional catalog, conservative English exclusion guard, no reliable out-of-domain detector and no human-rated recommendation usefulness. Get future sessions into the catalog before judging AI quality: the model intentionally does not run with an empty eligible set.
