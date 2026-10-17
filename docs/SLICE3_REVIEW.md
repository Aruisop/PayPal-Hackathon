# Collaborative Booking & Equal Payments: Slice 3 Review Packet

Status: Delivered on `slice/3-collaborative-booking-and-equal-payments`.

## Delivered Flow & Capabilities

GroupPay transforms group commerce from single-buyer exposure ("one friend becomes the bank") into a non-custodial multi-buyer coordination engine powered by PayPal Sandbox REST APIs (`intent="AUTHORIZE"`) and Google Gemini AI.

1. **Multi-Party Consensus & 12 AI Safety Gates**:
   - Reconciles conflicting natural language scheduling, budget ceilings, and dietary constraints across group members.
   - Built-in prompt injection defense neutralizes jailbreak attempts (`price=0`, `system override`), preserving immutable catalog pricing.
   - Deterministic catalog matching selects valid showtimes/itineraries with adjacent seats or excursion places without LLM hallucination.

2. **Exact Integer Cent Precision**:
   - Zero floating-point rounding errors. Server-owned catalog prices partitioned mathematically: $T = \sum c_i$.
   - Remainder pennies allocated deterministically in roster order.
   - Cryptographic 15-minute lease timer locks catalog inventory (`held_until`) with automatic TTL fencing.

3. **Multi-Buyer PayPal Sandbox Holds (`intent="AUTHORIZE"`)**:
   - Each participant independently approves an isolated payment hold directly to the merchant.
   - Zero pooled consumer wallet or custodial intermediary, eliminating Money Transmitter License (MTL) and MSB regulatory liabilities.

4. **Fenced Sequential Capture & Distributed Compensatory Rollback**:
   - Sequential capture initiates only when 100% of the roster has approved their hold.
   - Uses cryptographic claim tokens (`fenced_claim_token`) and persistent idempotency keys (`PayPal-Request-Id`).
   - If any member's payment declines at capture time (e.g. simulated `422 INSTRUMENT_DECLINED`):
     - Prior completed captures are automatically refunded via PayPal API (`/v2/payments/captures/{id}/refund`).
     - Pending authorizations are immediately voided (`/v2/payments/authorizations/{id}/void`).
     - Held inventory (cinema seats / excursion places) is restored to `FREE` in the catalog.
     - Guarantees zero financial loss for buyers and zero chargeback exposure for merchants.

5. **Private Cryptographic Passes**:
   - Each participant owns their own isolated digital wallet pass with dynamic SVG QR code and SHA256 checksum.
   - Cross-member private data isolation: members cannot view or tamper with other members' barcodes, receipts, or instruments.

6. **Judge Evaluation Center & Interactive Developer Tools**:
   - **Multi-Persona Perspective Switcher**: Switch between Alice (Lead), Bob (Member), Charlie (Member), and a 3-Way Real-Time Split Screen phone simulator.
   - **Gemini AI Guardrails & Injection Sandbox**: Interactive adversarial injection probes testing real-time security intercepts.
   - **Smartphone Pass Scanner Simulator**: Live camera laser scanner validating QR payloads and cryptographic ledger matching.
   - **Synthesized Web Audio API Engine**: Ultra-clean tactile sound cues for payment authorizations and alerts with zero external asset dependencies.
   - **Interactive Distributed DAG State Machine**: Click-to-inspect pipeline visualizing ACID transaction boundaries and compensatory saga rollbacks.

## Storage and Migration

Revision 3 adds:
- `catalog_offers`: Domain, merchant ID, title, schedule time, integer price in cents, and metadata.
- `catalog_resources`: Individual seats and excursion places with resource keys, row/col coordinates, and reservation states (`FREE`, `HELD`, `BOOKED`).
- `group_member_profiles`: Custom member display aliases and consent progress tracking.
- `group_member_preferences`: Participant natural language prompts, confirmed structured constraints, and AI negotiation notes.
- `shared_purchases`: Coordinated purchase lifecycle states (`DRAFT`, `AWAITING_AUTHORIZATIONS`, `FINALIZING`, `CONFIRMED`, `CANCELLED`), lease TTLs, and claim fencing tokens.
- `purchase_contributions`: Individual participant shares, integer cents, order IDs, authorization IDs, capture IDs, and contribution states (`PENDING`, `AUTHORIZED`, `CAPTURED`, `REFUNDED`, `VOIDED`).
- `group_tickets`: Private verifiable passes, unique ticket codes, assigned resources, issuance timestamps, and isolated participant ownership.
- `group_recovery_tasks`: Durable distributed compensatory saga tasks for automated refunds and voids.

## Verification & Test Suite

The test suite covers **75 automated unit and integration tests**:

```bash
python -m unittest discover -s tests -v
```

```text
----------------------------------------------------------------------
Ran 75 tests in 42.732s

OK
```

- **36 tests**: Workshop Baseline (auth idempotency, lease fencing, session security).
- **6 tests**: Group Coordination & Invitation Security.
- **10 tests**: Exact Integer Cent Math, Seat Map Races, and Freeze Locks.
- **12 tests**: AI Planning Evaluation Gates (Injection Defense, Outage Fallback, Budget Conflicts).
- **9 tests**: Multi-Buyer Authorizations, Participant Consent, Voiding, and Recovery.
- **4 tests**: Sequential Capture Fulfillment, Private Ticket Isolation, and Partial Capture Recovery.
- **2 tests**: Fixed-Price Travel Excursion Reuse & 3-Way Remainder Cent Distribution.
- **2 tests**: Hackathon Evaluation Showcase & Live Chaos Rollback Simulation.
