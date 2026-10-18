# Collaborative payment operation policy

This describes the corrected coordinator, not production-payment certification. All automated provider evidence is mocked. Multiple captures cannot be one atomic transaction.

## Durable boundary

One purchase lease serializes all contribution, capture, cancellation and recovery operations. Every write checks the saved token and deadline. Network calls run after closing database transactions. A successor reconciles saved `STARTED` operations instead of assuming an interrupted worker did nothing.

`group_operations` has one durable record per contribution and operation kind, with a stable random request ID, target ID, known provider ID, state and timestamps. Known provider IDs are saved before subsequent detail requests. Recovery hydrates those IDs even if a crash interrupted the corresponding contribution update.

Application uniqueness and inventory ownership outlive provider idempotency retention. A retry does not create another purchase, contribution or ticket. Inventory is released only after cancellation obligations are resolved; elapsed time alone is insufficient.

## Endpoint-specific handling

| Operation | Reconciliation and retry policy |
| --- | --- |
| Create `AUTHORIZE` order | Omit payee routing. Validate authenticated order identity, contribution reference, amount/currency and seller. If no order ID survived, an explicit owner retry reuses the persisted request ID and payload only within six hours and the reservation deadline. Beyond that, retain unresolved state. |
| Authorize approved order | Require owner consent and authenticated `APPROVED` order. Save nested authorization ID, then validate its membership in that order or explicit related-order evidence. A started unknown authorization is read through order/authorization GET; it is not blindly re-posted. |
| Capture authorization | Persist intent/key before dispatch. Require the correct exact authorization. Save returned capture ID, then authenticate and validate completed capture evidence and linkage. Unknown/pending outcomes stop further capture/issuance until resolved. A started capture is not blindly re-posted. |
| Refund capture | Persist refund operation before dispatch; save returned refund ID before GET. Check the exact amount and capture linkage. Known pending refunds are polled with refund GET. An unknown refund without an ID remains a merchant investigation obligation; no speculative duplicate refund. |
| Void authorization | Reconcile authorization GET to `VOIDED`. HTTP 204 is a valid empty successful adapter response, but the coordinator still checks the actual authorization state. Lost responses can resolve on the next pass. Unknown voids are not assumed successful. |

The create-order endpoint documents six-hour default request-ID retention. The coordinator does **not** extend that assumption to authorize/capture/refund/void. Those operations carry stable request IDs but use conservative authenticated lookup after an uncertain dispatch. This trades availability for avoiding duplicate or untraceable money movement. A manual investigation path is a recorded limitation; deleting records or resetting the purchase is not a recovery procedure.

Official contracts checked during implementation: [order creation](https://developer.paypal.com/sdk/orders/v2/orders-create/), [SDK v5 authorization flow](https://developer.paypal.com/v5/checkout/auth-capture/), [authorization capture](https://developer.paypal.com/api/payments/v2/authorizations-capture), [void](https://developer.paypal.com/api/payments/v2/authorizations-void), [refund](https://developer.paypal.com/api/payments/v2/captures-refund).

## Completion, expiry and operator action

Each member approves only their own share. Verifying the last required authorization persists finalization intent. An organizer can execute the capture pass, or `python server.py recover` can resume it after browser loss. The command processes at most twenty purchases per invocation; schedule subsequent invocations deliberately. GET polling reads local state only.

The purchase becomes `CONFIRMED` only when every frozen contribution has validated completed capture evidence, exact shares sum to the quote, and the application still owns every held resource. Local resource booking and private ticket insertion commit together. Fulfillment is a controlled fictional catalog, not an external supplier.

A definite capture rejection begins compensation. Pending or unknown captures are reconciled before refund/void decisions. Failed or pending refunds and voids keep `RECOVERY_REQUIRED` visible and protect inventory. Only resolved obligations permit `CANCELLED` or `EXPIRED`. Post-confirmation customer cancellation is outside this prototype; the pre-confirmation endpoint rejects it.

Revision 4 quarantines pre-correction Slice 3 purchases and preserves their original evidence. It cannot infer which old tickets, approvals or recovery claims were real. Independent merchant review is required before any separate repair tooling is designed.
