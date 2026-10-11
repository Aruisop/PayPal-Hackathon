# Collaborative booking and equal payments: product requirements

Version 0.1 · 11 October 2026 · Proposed roadmap, not an implementation report

**Product promise:** Book together without making one friend become the bank.

**Prototype definition:** A group agrees on a movie screening or fixed-price travel excursion, accepts a merchant quote and equal shares, and individually approves PayPal Sandbox payments. The application coordinates reservation, payment and ticket issuance. AI helps the group turn conflicting preferences into a confirmed plan. Each participant owns their receipt and ticket.

This document specifies future work. It does not mark Slice 2 accepted, authorize a payment migration, or claim movie/travel booking, AI, authorizations, refunds or supplier integrations already exist. Implementation should proceed through the review gates below. Existing workshop purchases remain an independent supported flow.

## 1. Repo baseline and evidence

Snapshot: local branch `slice/2-group-coordination`, HEAD `29a31fc`. Slice 2 is staged but uncommitted. `dev/aarya` was discussed as an integration branch; it has not been created in this snapshot. Preserve the existing staged changes, `.env` and local database. Do not start from the older retail `master` branch accidentally.

| Existing component | Reuse | Boundary that must change for the proposed product |
| --- | --- | --- |
| `server.py` | Flask, participant sessions, Origin/CSRF checks, private routes, Waitress | New plan, quote, reservation and contribution routes |
| `storage.py` | SQLAlchemy Core; local SQLite and managed PostgreSQL plan; migrations 1 and 2 | New versioned tables; never rewrite applied payment migrations |
| `groups.py` | Invite joins, persistent memberships, organizer-only selection | Existing selection is workshop-specific; no roster freeze, quote or consent model |
| `checkout.py` | Ownership, durable attempts, request IDs, reconciliation and lease fencing patterns | Current flow is immediate `CAPTURE`, with no authorization/refund coordinator |
| `payments.py` | Sandbox OAuth, server-only HTTP adapter, order/capture lookup | Add separately reviewed authorize, authorization capture, void and refund operations |
| `public/` | Vanilla browser UI and PayPal SDK v5 | Booking wizard, group progress, reservation deadline and private tickets |
| `tests/` | Mock-provider and access-control fixtures | New money, reservation, AI and cross-adapter acceptance cases |

Current groups resolve a participant's workshop booking through the unique participant/workshop pair. That is not a sufficient identity for a new shared purchase: the same participant may buy seats for several screenings or trips. Add explicit purchase/contribution relationships rather than treating an old workshop payment as funding a new booking.

Recorded evidence: the Slice 2 packet reports 36 passing mocked tests and a two-client HTTP walkthrough. Slice 1 real Sandbox completion, access, separate-profile denial and restart results are user-observed. The new group browser UI and live PostgreSQL execution remain unverified. No new tests or Sandbox transactions were performed to write this PRD. See [Slice 1](SLICE1_REVIEW.md), [Slice 2](SLICE2_REVIEW.md), and [storage](STORAGE_HOSTING.md).

## 2. Audience, problem and product hypothesis

Primary audience: small groups of friends who want adjacent movie seats or one shared excursion and are reluctant to have someone fund the entire purchase. The organizer coordinates the plan but has no authority to pay for another participant.

The current workaround combines chat, a booking website, an upfront payer and later reimbursement. Our hypothesis is that one shared plan with exact shares and visible booking progress reduces coordination work and avoids that upfront payer. This is a hypothesis to test, not a claim based on completed user research.

Jobs to accomplish:

- Organizer: choose something everyone can attend and afford, invite the right people, and understand whether the group has booked.
- Participant: understand the plan, total cost, own share and cancellation consequences before approving payment; retrieve their own ticket afterward.
- Participating merchant: receive separately traceable payments for one agreed booking, prevent duplicate resource allocation, and resolve incomplete payment without misleading customers.

Product differentiation is the combination of confirmed group preferences, one merchant quote, independently owned payments and explicit reservation/recovery behavior. Equal arithmetic, invite links and PayPal buttons alone are not novelty. Do not claim first-to-market status without competitive research.

## 3. Final prototype scope

### Required

- One responsive browser application and shared coordination service.
- Two controlled booking adapters: a fictional cinema and a fictional excursion operator.
- Seed at least three movie offerings and two excursion offerings with different schedules/prices so planning can demonstrate a real conflict and a feasible alternative. Each group purchases one selected offering, not a multi-supplier itinerary.
- Movie scenario: one ticket per participant, equal-price adjacent seats for one screening.
- Travel scenario: one fixed-price group excursion at one departure time, with one assigned place per participant. No flight ticketing or hotel supply integration.
- USD only; test groups of two to four participants. This is the supported demo scope, not a claim about production capacity.
- One frozen participant roster and one immutable quote per payment round; equal shares differing by at most one cent.
- Meaningful AI preference interpretation, clarification and explanation of a deterministic shortlist, with user confirmation.
- Genuine PayPal Sandbox authorization and capture; persistent void/refund recovery for failed group fulfillment.
- Private individual receipts and demonstration tickets; shared progress with explicit disclosure consent.
- Working failure paths, durable restart recovery, setup instructions and evidence of both domain flows.

Both adapters may settle into the same configured Sandbox Business account. They demonstrate two booking domains, not two independently onboarded sellers. Product screens must label the merchant, Sandbox test money and fictional fulfillment clearly. No real cinema or travel affiliation is implied.

### Deferred

Arbitrary website checkout injection, browser extension, live supplier bookings, production money, pooled wallets, peer reimbursement, multi-merchant itineraries, marketplace routing, dynamic foreign exchange, discounts, mixed-price ticket categories, individual post-confirmation cancellation, automatic participant substitution, AI spending authority, SDK v6 and a merchant dashboard.

The eventual integration product serves participating platforms. A PayPal button does not supply booking API access or permission to act for its merchant. Real seller integrations require suitable consent and platform access; Sandbox availability does not establish production approval. [PayPal platform requirements](https://developer.paypal.com/platforms/get-started), [seller onboarding](https://developer.paypal.com/platforms/seller-onboarding).

## 4. Experience and screen requirements

The main interface should communicate decisions and consequences before it exposes technical identifiers. Use original visual assets and fictional merchant names.

| Screen | User action and required information |
| --- | --- |
| Choose an activity | Switch between Movies and Excursions; see merchant, schedule, location, availability and indicative price |
| Group lobby | Create/join a group, choose a display alias, see roster and organizer; explain browser-session identity and invite access |
| Plan together | Each member describes timing, budget and preferences; sees an editable interpretation with exact dates/time zone and confirms it |
| Suitable options | Explain which confirmed constraints each offer meets; show explicit conflicts or no matches; organizer selects an offer |
| Review the booking | Show seats/places, merchant quote, fees, total, currency, roster, each exact share, reservation terms and cancellation policy |
| Approve your share | Show the participant's amount and that PayPal will authorize a hold first; require consent to later capture if the agreed group booking proceeds |
| Group progress | Show reservation deadline, verified authorization progress and own detailed payment state; distinguish funds held from money captured |
| Tickets or recovery | On success, each participant opens their own ticket/receipt. On failure, show that tickets are unavailable and the actual void/refund/recheck status |

Happy path:

1. Organizer creates a movie group; friends join through an invite under their own sessions.
2. Each enters and confirms preferences. Conflicting budgets or times produce a useful clarification, not an invented recommendation.
3. Organizer selects a suitable screening and adjacent seats. Members review the authoritative quote and roster.
4. Organizer freezes the roster. The merchant reserves inventory for a displayed, server-owned deadline. The final quote binds that reservation and participant allocation.
5. Each member accepts the final terms and approves only their own share in PayPal. Approval is followed by server-side authorization verification.
6. Once every required contribution is authorized, the server coordinates inventory preparation and captures. It does not depend on a final browser callback staying open.
7. After all exact captures are verified completed and fulfillment is verified issued, show group confirmation and each member's private ticket.

Critical copy examples: "Your funds are authorized; you have not been charged yet", "Payment completed; booking confirmation is still being checked", and "Refund requested; PayPal has not confirmed completion". Never use "Booked" for approval, authorization, pending capture or unknown supplier state. Keep a plain next action visible and restore it after refresh.

## 5. Functional requirements

P0 means required for the final prototype. P1 means useful only after P0 is complete.

| ID | Priority | Requirement and acceptance condition |
| --- | --- | --- |
| F01 | P0 | Existing workshop checkout remains functional; its immediate-capture behavior and entitlements are unchanged |
| F02 | P0 | Group reads require membership; plan/roster selection requires organizer identity; repeat joins cannot create duplicate memberships |
| F03 | P0 | Joining closes at roster freeze. Members must consent to sharing aliases and coarse progress; raw receipts, provider IDs and personal budget text remain private |
| F04 | P0 | AI interpretations require participant confirmation. Deterministic matching uses only confirmed constraints and trusted offers |
| F05 | P0 | Offer quote and inventory come from the selected server-side adapter. Browser/model amounts, supplier IDs and deadlines are never authoritative |
| F06 | P0 | Quote snapshots bind merchant, offer/version, resources, gross total, fees, currency, roster, deadline and cancellation policy |
| F07 | P0 | Compute and persist shares in integer USD cents. Their sum equals the exact quote total; repeat requests return the same allocation |
| F08 | P0 | Every participant sees and accepts their exact share and group-failure policy before authorization. Organizer cannot accept or approve for them |
| F09 | P0 | New contribution attempts persist owner, correlation, amount, merchant, operation IDs and provider IDs before retryable network operations |
| F10 | P0 | Buyer approval creates no charge-confirmed state or ticket. Validate the saved order/authorization and its amount, currency, merchant and purchase correlation |
| F11 | P0 | Start finalization once under a persistent, fenced claim only when all required authorizations and the reservation are eligible |
| F12 | P0 | Verify completed captures and supplier fulfillment before issuing usable tickets. Pending/unknown outcomes cannot produce tickets |
| F13 | P0 | Expiry, cancellation and partial failure create durable recovery work: reconcile, void eligible authorizations, refund completed captures when fulfillment is canceled |
| F14 | P0 | Lost responses, duplicate requests, callbacks and restarts reuse saved operations. Ambiguous evidence blocks replacement purchases and premature inventory release |
| F15 | P0 | Each ticket and receipt is owner-protected; invite, group, order and reservation IDs are not private-resource authorization |
| F16 | P0 | Movies and excursions run through the same coordinator. Domain-specific inventory and fulfillment rules live in adapters |
| F17 | P0 | A server-side recovery runner resumes persisted work after restart; clients poll stored progress and may request an owner-checked recheck |
| F18 | P0 | Hosted execution uses managed PostgreSQL and HTTPS, or provide complete local judge-run instructions; test migration and restart preservation |
| F19 | P1 | Invite rotation, account recovery, outbound reminders and integration with one contracted real merchant |

## 6. Price, membership and ownership decisions

Equal split algorithm: for total cents `T` and frozen participants `N`, assign `T // N` cents to each. Give one extra cent to the first `T % N` participants in a stable server-recorded order. Example: $100.00 among three participants gives $33.34, $33.33 and $33.33. Show the rounding rule. Do not use floating-point division or recalculate a share after approval.

The quote contains all disclosed customer charges. Individual PayPal processing fees are merchant settlement details; do not silently subtract them from contributions or add them to the next payer's share. Prototype purchase amounts remain USD; any PayPal funding-source conversion is distinct from our split.

Before freeze, members may leave and organizer may change the draft. After freeze, there is no roster/price edit. A new plan requires cancellation/recovery of the previous round and new consent; it cannot bypass unresolved old attempts. Recommend a configurable 15-minute initial hold for the controlled demonstration, with a test clock for expiry cases; this is not a universal supplier guarantee.

Browser sessions identify application participants, not verified natural persons. One person could operate several profiles; do not claim identity verification. Session loss does not erase financial obligations. Preserve records for investigation and do not let a new profile claim an old contribution using an order ID.

## 7. Booking adapter and data boundaries

Use a small common interface rather than building a generic marketplace:

| Adapter operation | Required result |
| --- | --- |
| Quote | Authoritative offer/version, available resources, gross price/currency, policy and expiry |
| Reserve | Resource allocation bound to the frozen purchase, final quote and hold deadline; uniqueness prevents two groups taking one seat/place |
| Prepare fulfillment | Durable provisional allocation under a stable operation ID, keeping resources secured during capture/recovery |
| Issue | Idempotent creation of the assigned demonstration tickets after verified payment completion |
| Read status | Authoritative reservation/allocation/issuance state for lost-response recovery |
| Cancel | Idempotent cancellation of provisional fulfillment and release when it is safe |

Final prototype adapters must support reversible provisional allocation. A future supplier without that capability cannot be presented as supporting the same group-failure policy. An availability check is not a reservation, and a reservation is not a ticket.

For controlled inventory, the resource lifecycle is `FREE -> HELD -> ALLOCATED -> ISSUED`. Expiry may release `HELD` resources only after an atomic decision prevents preparation/capture for that round; outstanding authorization cleanup can continue afterward. Preparing fulfillment moves held resources to durable provisional allocation, and the initial hold timer must not free `ALLOCATED` resources during captures. Cancellation releases allocated resources only after the coordinator has resolved in-flight fulfillment and payment obligations. Unknown issuance/capture remains blocked for reconciliation or merchant investigation. The exclusive resource key includes screening/departure and seat/place, not only a generic seat label.

Proposed persistent additions, subject to architecture review:

- Offer and resource records scoped to an adapter; movie screening/seat and excursion departure/place metadata.
- Confirmed member preferences, interpretation version, consent and model-call provenance.
- Shared purchase with group, frozen roster, immutable quote, policy and lifecycle.
- Contribution unique by purchase/participant, exact share, consent and active attempt. Never fund two purchases with one old workshop booking.
- Group payment attempts with intent, order/authorization/capture identifiers and stable endpoint-specific operation IDs.
- Reservation, resource assignments, tickets, refund/void records and durable recovery tasks with claims and fencing.

Retain Python, SQLAlchemy Core and vanilla JavaScript. Extend the PayPal adapter where practical, but isolate the new group coordinator from `Checkout`'s workshop flow. New schema revisions must preserve existing records. SDK v5 remains; group authorization checkout and workshop capture checkout must load the matching intent without conflicting SDK instances on a page.

Operational requirements: backend-owned UTC deadlines with explicit user time zones; bounded network timeouts and paced recovery retries; no financial side effects from GET polling; logs that omit secrets, cookies and sensitive preference text; and a fresh setup path using pinned dependencies. The mobile flow must have labelled fields, keyboard access, visible focus, readable status text and no reliance on color alone. Webhooks may supplement authenticated reconciliation later; they are not a substitute for it or a mandatory extra integration in this prototype.

## 8. Payment and fulfillment lifecycle

Each participant approves a separate PayPal order. Multiple purchase units do not turn a standard order into a multi-buyer payment. The business merchant receives separate captures; the application has no consumer wallet or organizer-controlled pool. [PayPal order schema](https://developer.paypal.com/sdk/orders/v2/definitions/order_request).

Use `AUTHORIZE` for new shared purchases. Keep `CAPTURE` for existing workshops. Planned operations are order creation and `POST /v2/checkout/orders/{id}/authorize`, followed by Payments v2 authorization GET/capture/void and capture GET/refund/refund GET. Persist authorization IDs separately from order and capture IDs. [SDK v5 authorization](https://developer.paypal.com/v5/checkout/auth-capture/), [Payments v2 operations](https://developer.paypal.com/api/payments/v2).

Before each implementation phase, record exact endpoint idempotency support, retention and reconciliation behavior from official documentation. Do not copy the existing order-create/capture six-hour assumption onto every new operation. Permanent application uniqueness and operation fencing remain required after provider retention expires.

Proposed sequence: reserve inventory -> authorize each share -> secure provisional fulfillment -> capture shares -> verify all completed -> issue tickets -> verify issuance. Each transition persists before the next retryable operation. No database transaction spans PayPal or supplier network calls. This sequence is safe only for the declared adapter capabilities.

| Shared purchase state | Meaning / exit condition |
| --- | --- |
| DRAFT | Roster/preferences can change; no payment operations |
| AWAITING_AUTHORIZATIONS | Quote and roster frozen; inventory held; some participants still need authorization |
| FINALIZING | A server worker owns the fenced workflow; resources prepared and captures being resolved |
| CONFIRMED | Every exact required capture completed; assigned tickets issued and verified |
| RECOVERY_REQUIRED | Capture, supplier or recovery outcome remains unresolved; tickets unavailable |
| CANCELLING | Cancellation intent persisted; financial and fulfillment obligations being resolved |
| CANCELLED / EXPIRED | No usable fulfillment and all known financial obligations resolved; reason distinguishes cancellation from deadline expiry |

Authorization, capture and refund states remain separate records. A held amount is not a paid amount. An elapsed deadline alone cannot prove cancellation: an in-flight operation may have completed. If issuance times out, query supplier status before deciding to cancel/refund an already issued booking.

Several captures cannot be made one atomic transaction. If the third capture fails after two complete, stop new captures, resolve the failure, cancel provisional fulfillment where safe, refund completed captures and void remaining eligible authorizations. If a capture is pending, preserve recovery state and reconcile; do not assume it can immediately be refunded. A refund request is not a completed refund. [Pending-capture restriction](https://developer.paypal.com/api/payments/v2/errors/pending_capture/), [refund states](https://developer.paypal.com/api/payments/v2/definitions/refund/).

The customer promise is coordinated booking with explicit recovery, not a guarantee of simultaneous charging or instant money return. Automatic customer-requested cancellation after confirmed ticket issuance is out of prototype scope; failed fulfillment still requires recovery.

## 9. AI product requirement

AI must materially improve group planning to satisfy the hackathon brief. A decorative chatbot or use of AI only to write code does not meet this PRD's product goal.

Inputs: consented preference text, participant time zone, reference date, booking domain and trusted offer attributes. Never send PayPal credentials, session tokens, transaction IDs or passenger identity documents to the model. Travel uses fictional travelers and excursion requirements, not passports or flight passenger records.

Structured output: interpreted date/time windows, per-person budget cents and currency, hard constraints, soft preferences, source text spans and explicit clarification questions. Ambiguous "next Friday", unstated currency or vague time references require confirmation. Do not treat an uncalibrated model confidence score as financial authority.

Participants edit and confirm interpretations. Ordinary code filters authoritative offers against confirmed hard constraints and computes exact shares. The model can explain the validated shortlist and conflicts using checked offer IDs and facts. It cannot invent purchasable inventory, set price, waive constraints, accept consent or call payment/booking operations.

Example: one member requests a Saturday evening movie under $20; another needs to finish before 9 pm; a third asks for adjacent seats. The system identifies the time conflict for a late screening and explains a feasible earlier option if the trusted catalog has one. If no option exists, it asks which constraint the owner wants to change. For a group-priced excursion, feasibility uses the actual frozen-roster split, including rounding and fees.

Failure behavior: invalid output is rejected, prompt injection cannot grant tools/permissions, and timeouts offer manual constraint entry. Manual fallback preserves usability but does not count as a successful AI demonstration. Raw budgets/text stay private; sharing derived group explanations that may reveal constraints requires explicit consent.

Evaluation gate: at least 12 labelled cases spanning movie/travel input, relative dates, currency ambiguity, conflicting budgets, unavailable adjacent seats, no matching offer, prompt injection, invalid schema and model outage. All hard-constraint boundary cases must remain fail-closed. Record expected results and actual model evidence; no invented pass rate.

## 10. Phased implementation and review gates

Phases are dependency order, not promises of delivery dates. The official rules currently list a submission deadline of 12 November 2026 at 12:00 pm Pacific Standard Time; recheck the portal before release. [Official rules](https://paypalaihackathon.devpost.com/rules).

| Phase | Implementation outcome | Exit gate |
| --- | --- | --- |
| 0 — Close the existing base | Review Slice 2, test its actual two-profile browser flow, preserve workshop evidence, establish the chosen integration branch | Known QA limitations recorded; reviewed base identified; no implicit merge or `dev/aarya` publication |
| 1 — Movie plan and exact shares | Controlled movie catalog, group draft, aliases/consent, roster freeze, authoritative quote and persisted cent allocation; no new money movement | Tampering, duplicate freeze, late join, rounding, quote expiry and cross-member access tests pass |
| 2 — AI-assisted agreement | Structured interpretation, clarifications, confirmed constraints and explained deterministic movie shortlist | Real model call shown; evaluation cases pass safety boundaries; no-match and outage UX works |
| 3 — Reservation and authorization | Persistent movie holds, group-specific contributions, SDK v5 authorize intent, provider validation, void and interrupted-authorization recovery | Real Sandbox authorization/void observed; expired/missing/unknown and concurrent-operation mock tests pass; no ticket issued |
| 4 — Complete or recover the movie booking | Provisional inventory allocation, fenced capture coordinator, private tickets, persisted refund/void tasks and server-side recovery runner | Real multi-participant Sandbox success and refund evidence; partial/unknown/pending failures, restart and seat races pass; no duplicate ticket/charge |
| 5 — Prove reuse with travel | Fixed-price excursion adapter, departure/place resources, travel preferences and tickets using the same coordinator | Real Sandbox excursion flow works; $100/3 rounding case; no cinema-specific branches in shared payment logic |
| 6 — Judge-ready release | Responsive/accessibility QA, managed PostgreSQL verification or complete local setup, licence decision, instructions, video and submission evidence | Final acceptance matrix complete; fresh setup succeeds; claims match recorded evidence |

After deterministic checks, each slice changing payments, access, concurrency, memberships or AI boundaries gets one independent read-only adversarial review. Provide the slice contract, diff and necessary referenced code without builder rationale. Cap findings at three; require location, violated requirement, reproduction/failing test, severity and reproduced/unverified status. Fix reproduced high-impact findings in one targeted revision and rerun affected checks. Record unresolved concerns and actual token telemetry where available; do not fabricate costs or repeat a review loop without a concrete failure.

If capacity runs short, finish movie success/recovery and real AI before expanding the second adapter. A movie-only fallback must be labelled reduced scope and must not be advertised as the full cross-domain prototype. Do not save time by dropping authorization safety, recovery or meaningful AI.

## 11. Required failure and acceptance cases

| Case | Required behavior |
| --- | --- |
| Client changes total/share/currency/merchant | Server ignores or rejects it; exact trusted quote is used |
| Two groups select the same seat | One reservation wins; the other receives a truthful availability error |
| Member joins/leaves after freeze | Frozen allocation remains unchanged; no silent amount reassignment |
| Quote changes before authorization | Stop and obtain a new quote/consent; never charge the revised value implicitly |
| Approval/authorization response lost | Reconcile known order/authorization; preserve unresolved attempts when evidence is insufficient |
| Browser refresh before callback | Owner resumes from persistent state; no dependence on the SDK repeating a callback |
| Two workers finalize concurrently | Fenced operation claims prevent duplicate capture/issuance; stale workers cannot commit |
| Deadline passes during authorization/capture | Serialize the terminal decision and reconcile in-flight work; do not release/replace blindly |
| One member never authorizes | Resolve/void other holds and release reservation safely; no successful group ticket |
| Third capture fails after two complete | Recovery remains visible; eligible completed captures refunded and remaining authorizations voided |
| Capture pending or unknown | No ticket; keep resource/recovery policy explicit; reconcile without another charge |
| Supplier prepare/issue response lost | Read supplier status under the saved operation ID before repeating or compensating |
| Refund/void response lost or pending | Persist and reconcile; do not display completed recovery prematurely |
| Server restarts in finalization/recovery | Runner resumes saved tasks with fencing; same payment IDs and ticket allocations |
| Outsider/member requests another receipt/ticket | Access denied even with correct group/order/ticket identifiers |
| AI invents offer/price or violates a hard constraint | Reject output or exclude option; payment values never change |
| Cookie disappears | No reassignment via transaction ID; provide support guidance and retain financial records |

Final evidence must distinguish mocked failures, controlled supplier fulfillment, real model calls and real PayPal Sandbox operations. OAuth is connectivity evidence only. Authorization is held-funds evidence only. Completed capture is payment evidence, not proof of supplier issuance.

## 12. Design validation and final acceptance

Proposed usability check: five peers who were not involved in implementation attempt the flow. Target at least four correctly distinguishing a hold, a completed payment and a confirmed booking, identifying their share, and finding the next action after failure without developer explanation. These are targets, not existing results. Ask whether they would use it and what makes them uncomfortable; do not treat five interviews as proof of market demand.

Final prototype passes only when:

1. Both booking domains work through one group/payment coordinator with controlled, labelled inventory.
2. At least one real AI interaction changes the group's plan by interpreting/clarifying constraints; deterministic rules preserve all confirmed hard constraints.
3. Separate browser profiles approve their own exact shares through genuine Sandbox checkout; payment and ticket ownership remain independent.
4. Confirmation requires every required completed capture and verified issued fulfillment; participant/merchant/amount/currency correlation is checked.
5. The failure matrix, rounding, migration, restart and authorization boundaries have meaningful automated coverage, with mocked provider responses labelled.
6. A real Sandbox success flow is recorded in each domain, and authorization/void/refund operations needed for recovery are separately verified. Do not present a scripted fake-provider failure as a live PayPal result.
7. PostgreSQL is actually tested before claiming a hosted demo. Otherwise deliver a complete local run path and disclose the hosting gap.
8. Existing workshop purchases and entitlement access still work without altered historical prices or deleted data.
9. No credentials, cookies, local databases or generated archives enter public source. Judge access is arranged through controlled test instructions or a secure hosted flow, not published API secrets.
10. The public repository has the team-selected open-source licence, pinned setup, required tools/env documentation and evidence; the functional video is publicly available on YouTube and under three minutes. The working project remains available through the judging period under the official rules. [Submission requirements](https://paypalaihackathon.devpost.com/rules).

## 13. Submission story and demo

Pitch: "Friends agree on one booking and approve their own shares. AI helps resolve the planning conflicts; PayPal handles the individual payments; our coordinator makes booking and failure progress understandable. Nobody has to front the group's total."

| Demo time | Show actual functionality |
| --- | --- |
| 0:00–0:20 | A three-person group and the problem: adjacent seats without an upfront payer |
| 0:20–0:50 | Conflicting natural-language constraints, confirmation and a supported option with a factual explanation |
| 0:50–1:15 | Frozen seats/quote/roster, exact shares and clear authorization terms |
| 1:15–2:05 | Actual Sandbox checkout across profiles, progress from holds to captures, then private ticket access and another member's denial |
| 2:05–2:30 | Excursion adapter using the same interface/coordinator; show persisted booking and cent allocation |
| 2:30–2:50 | A clearly labelled injected failure and its genuine recovery UI; identify mock versus Sandbox evidence |

Use pre-authenticated test accounts and edited waiting time if necessary; never substitute staged UI for an unbuilt flow. Keep original assets and avoid unlicensed movie posters, logos or music. Judges should understand the successful path before seeing failure diagnostics.

Judging alignment: implementation is demonstrated by real PayPal operations plus meaningful AI; design by clear consent and recovery screens; impact by the specific organizer/participant problem; innovation by shared fulfillment with separate ownership; presentation by a complete, evidence-backed story. These are evaluation goals, not a promise of winning.

## 14. Decisions still needed before release

The product direction above is recommended. Team decisions remain: acceptance of Slice 2; choice/creation of an integration branch; AI provider and access budget; public licence; local versus hosted judging path; ownership of each phase; consent wording and cancellation policy; and the time available before submission. Do not claim PayPal endorsement, a real supplier relationship or a chosen deployment while those decisions are pending.

Known provider limit: PayPal documents authorization validity of up to 29 days and recommends capture within the first three. It also documents that Sandbox authorizations do not expire the same way, so expiry must be exercised with controlled failure tests rather than waiting for Sandbox behavior. Reservation deadlines remain supplier-owned. [Authorization testing and limits](https://developer.paypal.com/checkout/delay-capture/).

Future real-platform onboarding is a separate validation effort: prove booking API access, multiple-payment acceptance, provisional allocation, cancellation/refund rights and merchant authorization for each supplier. Platform reuse is an interface design goal; universal compatibility is not a prototype claim.
