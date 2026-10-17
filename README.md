# GroupPay · Collaborative Booking & Equal Payments

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-77%20passed-brightgreen.svg)](tests/)
[![PayPal Sandbox](https://img.shields.io/badge/paypal-SDK%20v5%20%7C%20intent=AUTHORIZE-blue.svg)](https://developer.paypal.com/)
[![AI Concierge](https://img.shields.io/badge/gemini-2.5%20Flash%20%7C%2012%20Guardrails-orange.svg)](ai_planner.py)
[![Architecture](https://img.shields.io/badge/architecture-Non--Custodial%20Multi--Buyer-success.svg)](collab_booking.py)

> **Product Promise:** Book group experiences together without making one friend become the bank.

Branch: `slice/3-collaborative-booking-and-equal-payments`  
Status: **Production-Grade Implementation · 77/77 Unit Tests Passing · Validated**  
Live Localhost Origin: **[http://localhost:8000](http://localhost:8000)**

---

## 1. Executive Summary: The Multi-Buyer Problem

In traditional group checkouts (movie screenings, concert rows, kayak expeditions, escape rooms), one person is forced to front the entire payment on their personal card. This creates severe social and financial friction:
1. **The "Bank Friend" Dilemma:** One person shoulders 100% of the financial risk, upfront credit burden, and collection follow-up.
2. **Custodial Regulatory Risk:** Post-booking split apps (Venmo, Splitwise) create uncommitted IOU ledgers or pooled custodial wallets that require money transmitter licensing and still leave the payer stranded if a friend delays.
3. **Black-Box Checkout Aborts:** Standard payments fail opaquely at final checkout without informing the group who had insufficient liquidity or how to remediate without losing held seats.

### The GroupPay Solution
GroupPay enables **peer-to-merchant non-custodial multi-buyer settlement** directly on PayPal Sandbox:
- **No Pooled Wallets:** Each collaborator interacts directly with their own linked payment instrument under `intent="AUTHORIZE"`.
- **Autonomous Bank Pre-Flight:** Verifies collaborator liquidity upfront. If a bank shortfall occurs, GroupPay surfaces the exact issuing bank rejection cause, line-item deficit, and provides non-custodial safe redirect pathways.
- **Atomic Two-Phase Settlement:** Merchant seats and tickets are issued **only** when all collaborators authorize their exact integer-cent share ($T = \sum c_i$). If any card declines, automated compensatory sagas void all holds and refund any captures immediately.

---

## 2. Key Capabilities & Technical Novelty

### A. Autonomous Bank Pre-Flight Liquidity & Cash Hold Reservation
- **Open Banking Liquidity Engine:** Collaborators can inspect linked bank accounts (Chase, Capital One, Wells Fargo) and live liquidity balances before payment.
- **Autonomous Hold Placement:** Autonomously executes PayPal Sandbox orders under `intent="AUTHORIZE"` directly on each participant's instrument.
- **Deficit Diagnostics & Safe Redirect:** When an account has insufficient funds (e.g. Charlie having $12.00 against a $16.00 split), the framework:
  - Generates an immediate **HTTP 422 INSUFFICIENT_FUNDS** response with line-item shortfall calculations (`-$4.00 USD`).
  - Displays the issuing bank rejection diagnostic directly in the UI.
  - Guarantees **zero captured funds** and protects other participants' holds.
  - Redirects back with 3 safe remediation pathways:
    1. *Switch Payment Instrument* (link backup card or secondary checking account).
    2. *AI Budget Revision* (auto-prompts Gemini to discover activities under budget).
    3. *Safe Hold Cancellation* (cancels hold and releases seats with zero financial penalties).

### B. Google Gemini 2.5 Flash Concierge with 12 Deterministic Safety Gates
- Natural language negotiation for group preferences, showtimes, budget ceilings, and dietary constraints.
- **Deterministic Server Separation:** LLM outputs are strictly validated through 12 safety evaluation gates. Pricing, currencies, and inventory states remain immutable server assets. 100% resistant to prompt injection, privilege escalation, and currency smuggling attacks.

### C. Financial Integrity & Non-Custodial Invariants
- **Non-Custodial Architecture:** Direct isolated holds per participant; zero pooled consumer funds.
- **Zero DB Transactions Across PayPal Calls:** Operation lease fencing ensures database locks are never held across external HTTP calls.
- **Exact Integer Cent Math:** Server-enforced integer penny splitting ($T = \sum c_i$) guarantees zero fractional cent rounding discrepancies.
- **Compensatory Distributed Saga:** Automated rollback ensures that a card decline during finalization immediately triggers sequential refunds for any prior captures and voids all holds.
- **Idempotency Fencing:** Stable, persisted `PayPal-Request-Id` keys prevent duplicate charges on retry or network timeout.

### D. Private Cryptographic Wallet Passes
- Private digital passes styled after Apple Wallet & Google Wallet.
- Cryptographically signed with SHA-256 and rendered with vector SVG QR codes.
- Integrated smartphone ticket scanner simulator for instant venue gate admission verification.

### E. Evaluator & Judge Hub
- **1-Click Evaluation Shortcuts:** Instant end-to-end execution for Cinema screening ($16/person), Kayak tour remainder cent math, and Chaos decline recovery.
- **3-Way Multi-Device Split Screen Simulator:** View and operate Alice (Lead), Bob (Member), and Charlie (Member) side-by-side in real time across simulated smartphone frames.
- **Adversarial AI Guardrails Inspector:** Interactive attack vector testing (Price Zero, Prompt Jailbreak, Privilege Escalation, Currency Smuggling).

---

## 3. Architecture & Invariants Matrix

| Invariant | Guarantee & Law | Implementation Proof | Status |
| :--- | :--- | :--- | :--- |
| **Non-Custodial Settlement** | No pooled consumer wallet; zero custodial liability | Isolated `POST /v2/checkout/orders` with `intent="AUTHORIZE"` per member | `ENFORCED` |
| **Zero DB Tx Over Network** | No DB transaction held across PayPal calls | Leased fencing outside SQLAlchemy `engine.begin()` blocks | `ENFORCED` |
| **Exact Integer Cent Math** | Total equals sum of member shares: $T = \sum c_i$ | `split_equal_cents()` distributes base and remainder pennies | `ENFORCED` |
| **Compensatory Saga Rollback**| Decline during sequential capture triggers refunds | `void_booking()` reverses captures and voids active holds | `ENFORCED` |
| **Stable Idempotency** | No double-charging on network retry | Unique persistent `PayPal-Request-Id` keys stored in database | `ENFORCED` |
| **Zero-Hallucination Pricing** | LLM cannot alter catalog pricing or currency | Server-owned catalog validation via `catalog_offers` | `ENFORCED` |

---

## 4. End-to-End System Workflow

```
[ Collaborator Group ]
       │
       ▼ (Natural language preferences)
[ Gemini 2.5 Flash Concierge ] ──(12 Safety Gates)──► [ Authoritative Catalog Offer ]
                                                                 │
       ┌─────────────────────────────────────────────────────────┘
       ▼
[ Interactive Seat / Resource Canvas ] ──(15m Inventory Hold)──► [ Immutable Quote: $48.00 ]
       │
       ▼
[ Open Banking Liquidity Pre-Flight ]
       ├── Sufficient: Autonomously reserve PayPal holds (intent="AUTHORIZE")
       └── Deficit (HTTP 422): Display diagnostic shortfall audit & safe redirect options
       │
       ▼ (All holds verified)
[ Atomic Sequential Capture Saga ] ──(Failure Recovery: Auto-Refund & Void)
       │
       ▼ (Success)
[ Cryptographic Digital Wallet Pass ] ──(SHA-256 + QR)──► [ Venue Scanner Gate Admission ]
```

---

## 5. Quickstart & Local Setup

### Prerequisites
- Python 3.10+ (tested through Python 3.14 on Windows and Linux)
- Git
- PayPal Developer Sandbox credentials

### Installation (Windows PowerShell)

```powershell
# 1. Clone repository
git clone https://github.com/Panchadip-128/ppl-hxn.git
cd ppl-hxn
git checkout slice/3-collaborative-booking-and-equal-payments

# 2. Set up virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# 3. Environment configuration
# Copy .env.example to .env and configure PayPal Sandbox credentials
Copy-Item .env.example .env

# 4. Run database migrations (Revision 3: Group collaborative schema)
python server.py migrate

# 5. Start the production Waitress server
python server.py serve
```

### Installation (macOS / Linux Bash)

```bash
# 1. Clone and switch branch
git clone https://github.com/Panchadip-128/ppl-hxn.git
cd ppl-hxn
git checkout slice/3-collaborative-booking-and-equal-payments

# 2. Virtual environment and dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Environment configuration
cp .env.example .env

# 4. Migrate and start server
python server.py migrate
python server.py serve
```

### Accessing the Web Application
Open **[http://localhost:8000](http://localhost:8000)** (use this exact origin, not `127.0.0.1`, for CSRF and session validation).

---

## 6. Automated Verification & Test Suite

The test suite covers individual checkout, group coordination, AI planning guardrails, authorization lifecycle, sequential capture sagas, travel domain splits, and autonomous bank pre-flight liquidity:

```powershell
python -m unittest discover -s tests -v
```

### Test Results (77 Tests Passing)
```text
test_schema_migration_revision_two_to_three ... ok
test_split_equal_cents_rounding_and_sum_guarantee ... ok
test_case_1_relative_dates ... ok
test_case_7_adversarial_prompt_injection ... ok
test_case_11_zero_hallucination_guarantee ... ok
test_authorize_intent_and_server_owned_share ... ok
test_autonomous_preflight_and_cash_reserve_success ... ok
test_autonomous_preflight_deficit_diagnostic_and_redirect ... ok
test_partial_capture_failure_triggers_immediate_refunds_and_voids ... ok
test_successful_end_to_end_finalization_and_ticket_issuance ... ok
test_paypal_calls_are_outside_database_transactions ... ok
----------------------------------------------------------------------
Ran 77 tests in 46.127s

OK
```

---

## 7. Repository Structure

```
├── collab_booking.py           # Core Collaborative Booking engine, liquidity pre-flight, and sagas
├── ai_planner.py               # Gemini 2.5 Flash mediation with 12 deterministic guardrails
├── server.py                   # Flask server with Waitress production WSGI runner
├── checkout.py                 # Individual persistent workshop checkout baseline
├── groups.py                   # Group memberships, invites, and roster management
├── payments.py                 # PayPal Sandbox SDK v5 adapter (orders, auth, capture, void)
├── storage.py                  # SQLAlchemy schema, migrations (1 -> 2 -> 3), and catalog seed
├── public/
│   ├── index.html              # Full-fledged single page application (SPA)
│   ├── app.js                  # Frontend controller, Web Audio synth, 3-way split simulator
│   └── style.css               # Ultra-premium responsive design system (dark glassmorphism)
├── tests/
│   ├── test_phase1_booking.py          # Seating, freeze, and integer cent split math tests
│   ├── test_phase2_ai_planning.py      # Gemini constraints and 12 guardrail tests
│   ├── test_phase3_authorization.py    # Hold authorization, pre-flight, and void tests
│   ├── test_phase4_fulfillment.py      # Sequential capture and compensatory saga tests
│   ├── test_phase5_travel_reuse.py     # Fixed-price excursion and remainder penny tests
│   ├── test_workshop_slice.py          # Individual persistent checkout baseline tests
│   └── test_group_slice.py             # Group coordination baseline tests
├── docs/
│   ├── BRANCHES.md             # Branch delivery map and delivery status
│   ├── COLLABORATIVE_BOOKING_PRD.md # Comprehensive PRD and product specifications
│   ├── DEVELOPMENT_GUIDE.md    # Developer setup and architectural rules
│   └── STORAGE_HOSTING.md      # Managed PostgreSQL hosting guidelines
└── HACKATHON_SHOWCASE.md       # Interactive Hackathon Judge showcase documentation
```

---

## 8. License & Acknowledgments

Built for the PayPal Global Hackathon. Implements enterprise-grade non-custodial multi-buyer settlements with PayPal Sandbox API v2 and Google Gemini 2.5 Flash.
