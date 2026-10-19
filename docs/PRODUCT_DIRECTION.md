# Hackathon ideas and development principles

> Context: Historical proposals predating the workshop pivot. This is not the current implementation or authorization to start features. See [branch map](BRANCHES.md) and [current Slice 1 review](SLICE1_REVIEW.md).

Planning note, 4 October 2026. These are proposals, not implemented features or a selected product commitment.

## Challenge constraints

The supplied challenge brief requires meaningful use of both PayPal and AI, a working prototype, and documentation. Submission also requires a public open-source repository with a visible license, a runnable setup or hosted demo, a feature/tool description, and a public YouTube demo under three minutes. No prescribed track or problem statement is provided.

The judging criteria are implementation, design, impact, innovation, and presentation. Prioritize a specific audience, an observable problem, and a complete workflow over a long feature list. Add an appropriate license before submission; the current repository has no license file. Choosing a license is a separate project decision.

## Starting point

The repo contains a Python standard-library server and a plain browser UI. Existing functionality is Sandbox order creation/capture, receipts, decline simulation, cancellation handling, and UI-only simulation. Existing tests mock PayPal and test local HTTP behavior. Real Sandbox payment was reported working using a US buyer with an IN seller.

There is no AI integration, database, user authentication, webhook processing, or durable reconciliation. Treat the payment adapter as reusable infrastructure, not a complete product backend. See [the development guide](DEVELOPMENT_GUIDE.md) for current limitations.

## Candidate ideas

| Idea | Audience and problem | Meaningful AI | Meaningful PayPal | Relative effort from this repo |
| --- | --- | --- | --- | --- |
| Just One More | Independent video editors handling ambiguous briefs and unpaid extra requests | Extract scope, inspect short delivered videos, and compare new requests against approved scope with evidence | Pay for accepted work and separately approved additions; link each receipt to the exact scope version | Medium; recommended |
| Brief-to-basket | Small workshop organizers translating an event description into supply orders | Match needs against a fixed merchant catalog, explain alternatives, flag unavailable requirements | Checkout for the chosen catalog items | Lower; narrow catalog essential |
| Checkout companion | Small merchants serving buyers who struggle with payment language | Explain real checkout state and errors in the buyer's preferred language | Actual approval/capture and factual transaction status | Lower; useful but harder to differentiate |
| Refund review desk | A single merchant evaluating inconsistent customer refund requests | Compare a request with merchant policy and purchase evidence; draft a review recommendation | Look up actual captures and execute seller-approved refunds | Higher; new API, access controls, partial refund accounting |

Effort is comparative, not a schedule estimate. Team size, available time, model access, and deployment requirements remain unknown.

## Recommended concept: Just One More

Tagline: **Small request. Clear agreement.**

The name comes from the familiar client request for one more edit. It speaks directly to video editors and the moment this product helps with. Name, trademark, and domain availability have not been established.

The concept now adds reviewable evidence from the actual delivered video while keeping the scope/approval/payment workflow. Read the [feasibility assessment](FEASIBILITY.md) before implementation: objective media checks can be exact, while model findings require evaluation and human review.

Start with one audience: independent video editors working with overseas clients. The hypothesis is that a clearly priced change request can prevent unpaid revisions and uncertainty about what an earlier payment covered. Validate this with actual freelancers before claiming impact.

Example: a client requests one 30-second vertical video, captions, and two revisions. Later they ask for a second horizontal version and another revision. The app identifies the new deliverables, cites the earlier scope, and asks whether to quote an addition. It does not silently turn every request into a fee.

### First ripple: useful clarity

Paste a brief. AI proposes deliverables, exclusions, revision count, deadline, and unresolved questions. Each important extracted claim includes an exact source excerpt. Unknown details remain unknown: “a few versions” is a clarification question, not an invented quantity.

The seller edits the scope and selects services from a small rate card. Deterministic code calculates amounts in integer minor units. AI does not decide final prices. The buyer reviews a plain summary before accepting and paying through PayPal.

### Second ripple: changes become explicit

Paste a later client request. AI compares it with the accepted version and proposes one of three outcomes: included, possible added scope, or needs clarification. Show supporting excerpts from both messages. The seller reviews the interpretation, edits a priced addition, and the buyer explicitly approves it before a new PayPal checkout.

Make this the hero feature. A proposal generator alone overlaps existing products. The differentiated hypothesis is an evidence-backed scope difference tied to a separate, approved payment.

### Third ripple: reliable history

Keep scope versions, decisions, order IDs, capture IDs, and status in SQLite. Accepted scope versions are immutable. An amendment creates another version and records its relationship to earlier paid work. Every receipt answers “what did this payment cover?”

Store capture request IDs before issuing network requests. Reconcile uncertain payment outcomes with PayPal rather than marking timeout as failure or blindly retrying. Verified capture webhooks can update state after the browser closes. Do not call this escrow: payments are ordinary merchant captures; the app holds no client funds and guarantees no dispute outcome.

### Later ripples, only after the core works

Add multilingual summaries, reusable service templates, and exports of the scope/payment timeline. After usability validation, integrate approved requests into existing project tools through a small API. Multi-merchant onboarding, automatic reminders, subscriptions, and arbitrary autonomous spending are outside the first prototype.

## Smallest credible hackathon build

Use one configured seller, one service category, one rate card, one currency, and two demo roles. The two roles must be clearly labeled in a local demo; a hosted app needs actual access control and protected buyer links rather than a role switch that gives everyone merchant access.

Deliver:

1. Brief input and a real AI-generated structured draft with source evidence and missing-detail questions.
2. Seller editing, deterministic pricing, and buyer review of an accepted immutable scope.
3. Real Sandbox checkout tied to that version, with a receipt and persisted payment state.
4. A subsequent client request, AI scope comparison, and seller-reviewed addition.
5. A second buyer-approved checkout plus a timeline showing both scopes and payments.
6. A graceful decline and a useful explanation of uncertain payment status.

Keep reminders, OCR, mailbox integrations, recommendations from an unrestricted catalog, team management, and dashboards out of the first slice. Build each slice vertically through UI, domain logic, storage, and payment where applicable.

## Simple implementation boundaries

Keep feature modules under `app/`; avoid rewriting the working integration in one step:

```text
app/
  ai.py          # Model calls and validated result objects
  scope.py       # Scope versions, review decisions, deterministic pricing
  payments.py    # PayPal adapter and status mapping
  storage.py     # SQLite queries and transactions
  routes.py      # Request validation and orchestration
public/          # Browser views
tests/           # Domain, adapter, payment, and AI evaluation cases
```

Simple interfaces to aim for:

```text
draft_scope(brief) -> ScopeDraft
compare_request(accepted_scope, request) -> ChangeSuggestion
price_items(rate_card, selected_items) -> Money
create_checkout(accepted_scope_version_id) -> CheckoutOrder
reconcile_payment(local_order_id) -> PaymentStatus
```

AI suggestions must never directly create payments. The payment function loads the accepted version and authoritative amount from storage. Model provider details stay inside `ai.py`; PayPal details stay inside `payments.py`. No agent framework is necessary for this workflow. Pick an actively maintained HTTP framework if deployment needs it, without introducing microservices.

Use a small explicit state machine: scope draft/review/accepted; payment created/awaiting approval/capture pending/completed/failed/unknown. Define allowed transitions, especially unknown and pending outcomes. Resolve those outcomes from PayPal evidence, not model text. Keep money and scope states separate.

## Reliability principles to keep while developing

- Validate input and model output against explicit schemas; enforce size limits and server-side ownership.
- Use integer minor units plus explicit currency; do not calculate totals with binary floating point or trust AI arithmetic.
- Require seller review of proposed scope/pricing and buyer consent before each checkout. Acceptance here is a product action; do not claim legal enforceability.
- Treat client messages as untrusted data, including instructions embedded in the brief. The model has no credentials or payment tools. Validate that cited excerpts actually occur in the source; review whether they support the claim.
- Persist accepted versions, local order IDs, idempotency keys, capture IDs, and event processing results. Prevent duplicate processing and stale-version payments in database transactions.
- Do not hold a database transaction open while waiting for PayPal or the model. Record intent first, call the external service, then reconcile the result.
- Fail visibly on AI timeouts or invalid output; offer manual scope editing. Clearly label any fixture/replay mode, and keep a real AI path working for evaluation.
- Redact secrets from logs and minimize client-message logging. Do not send account credentials or unnecessary personal information to the model.
- Test behavior: duplicate capture/repeated webhook, wrong session, stale quote, model-invented quantities, ambiguous requests, and interrupted payment outcomes. Avoid tests that only restate helper implementations.
- Keep secrets in local ignored config; keep safe templates empty. Extend ignore rules deliberately if new environment files or local databases are introduced.

## Validate usefulness and AI quality

Interview three to five freelancers with specific examples: what was requested, what changed, how they handled pricing, and whether the client understood. Ask them to use the draft and change comparison; record whether they corrected the output and whether they would use it again. Do not treat interview count as proof of broad demand.

Create a small labeled evaluation set of original briefs and later requests: clearly included changes, clearly additional deliverables, ambiguous requests, conflicting revision counts, missing deadlines, and malicious instructions. Measure unsupported extracted facts, evidence accuracy, ambiguity detection, and mistaken extra-charge suggestions. Track latency and approximate inference cost. A false extra-charge suggestion is a product failure even when the model's prose sounds confident.

The three-minute demo should show one concrete job from vague brief to approved scope, Sandbox payment, a meaningful extra request, a reviewed amendment, and another payment. Include a quick decline recovery or ambiguous-request example. Explain what is actually implemented and what is future work.

## Differentiation and supporting references

Uniqueness is a hypothesis, not a claim that nobody has built a similar product. Bonsai already offers proposals, scope documents, invoicing, and an AI-native document builder. PayPal's agent toolkit already supports payment and invoicing workflows. Compare the concrete scope-change/payment trace rather than competing on a generic “AI invoice generator.”

- [Bonsai document builder](https://help.hellobonsai.com/en/articles/15879228-document-builder-overview)
- [Bonsai proposals](https://help.hellobonsai.com/en/articles/5616844-all-about-proposals)
- [PayPal agent toolkit](https://github.com/paypal/agent-toolkit)
- [PayPal checkout webhooks](https://developer.paypal.com/payment-methods/webhooks/)

Before implementation, confirm audience access, available development time, and access to an AI provider. Those affect scope; they do not change the principles of simple modules, explicit approvals, persistent payment truth, and narrow end-to-end delivery.
