# Group payment platform direction

## Core idea

**Split first, then pay.** A group chooses one merchant purchase, each person approves their own final share through PayPal, and the merchant booking completes only when all required payments succeed before the hold expires. No friend needs to pay the whole bill and request reimbursement later.

This is different from Splitwise-style debt tracking:

- **Splitwise:** one person usually pays first; the group settles later.
- **Group checkout:** the group agrees on shares first; each person pays the merchant directly.

## Delivered development slice: merchant checkout demo

The app now demonstrates this flow for fictional movie and excursion merchants. It is deliberately a merchant-owned checkout screen that appears before the PayPal approval window:

1. A buyer chooses an already trusted catalog offer and pays alone, or creates a fixed two-to-four-payer checkout.
2. The server persists the merchant mode, trusted offer and intended roster count before the invite is shared.
3. Only the organizer can freeze the roster after exactly that number of members have joined. The server then selects available resources, creates a 15-minute hold and calculates the exact-cent equal shares.
4. Every payer separately consents to and authorizes only their own displayed share through the normal PayPal approval window.
5. The existing fenced capture/reconciliation workflow confirms the fictional order only after every required capture is verified completed. Incomplete, failed and unknown outcomes remain visible for recovery.

This is a controlled merchant app, not a reusable integration for outside booking sites. It deliberately reuses the existing server-owned quote, consent, payment-evidence and recovery protocol; the browser neither supplies a price nor calculates shares.

## What this development slice does not deliver

- A public SDK, merchant onboarding flow, webhooks, marketplace routing or a hosted PayPal-window customization.
- Live Sandbox/production settlement, rendered-browser approval evidence or hosted PostgreSQL verification.
- Unequal or AI-selected allocations. A future allocator may propose a split only; the server must validate the frozen total and every affected payer must explicitly accept it.
- A general-purpose bill-splitting or debt-settlement product.

## Platform direction

A participating merchant would integrate a group-checkout capability alongside its normal checkout. It supplies the authoritative total, currency, inventory hold, expiry, and booking result. The capability returns group-payment progress and only confirms the merchant booking after the required payments are completed.

Real integrations need merchant permission, booking/inventory APIs, temporary holds, cancellation/refund rules and a durable reconciliation contract. A PayPal button alone does not provide that access.

## AI role

AI is optional and cannot move money. It can:

- Help a group choose a merchant option based on confirmed preferences.
- Read a variable bill, such as a restaurant receipt, and suggest a share allocation.
- Explain the proposed split or ask for clarification.

Every person must review and approve their final amount. The merchant/server remains authoritative for prices, inventory, payment state, and booking confirmation.
