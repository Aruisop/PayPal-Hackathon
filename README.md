# GroupPay · Collaborative Booking & Equal Payments

Branch: `slice/3-collaborative-booking-and-equal-payments`. Status: **Implemented & Validated**.
For full hackathon judge evaluation details, architecture diagrams, and novelty analysis, see [HACKATHON_SHOWCASE.md](HACKATHON_SHOWCASE.md) and [COLLABORATIVE_BOOKING_PRD.md](docs/COLLABORATIVE_BOOKING_PRD.md).

> **Product Promise:** Book together without making one friend become the bank.

A group agrees on a cinema screening or fixed-price travel excursion, accepts a merchant quote and equal integer cent shares, and individually approves PayPal Sandbox payments (`intent="AUTHORIZE"`). The application coordinates reservation, payment, and private ticket issuance. Gemini AI reconciles conflicting natural language constraints with 12 deterministic safety evaluation gates.

An interactive **Hackathon Evaluation Center** is integrated directly into the web UI at **http://localhost:8000** for 1-click live multi-buyer simulation, chaos rollback testing, and architecture inspection.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# First setup only. Skip this copy if .env already exists.
Copy-Item .env.example .env
# Configure .env, then:
.\.venv\Scripts\python.exe server.py migrate
.\.venv\Scripts\python.exe server.py
```

Set `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` for your Business Sandbox app. `PAYPAL_MERCHANT_ID` is optional: it pins the expected seller for validation, never routes funds. Standard Checkout omits `payee`, so PayPal selects the API caller's account; the server persists the merchant ID from an authenticated order GET before capture. If an optional pin is wrong, capture/access stays blocked. Never commit `.env`. The longer [Sandbox account guide](README_setup_guide.md) is an account reference; this README governs the current workshop slice.

Open **http://localhost:8000** (use this exact origin, not 127.0.0.1). Missing app credentials disable checkout; a missing Merchant ID does not. No payment or entitlement is simulated. For the existing IN seller, use the working US Personal Sandbox buyer. Enter buyer credentials only in PayPal's checkout window.

Local SQLite data is stored in ignored `instance/workshops.db`; sessions, groups, memberships and bookings survive restart. Run `server.py migrate` before starting updated production code; revision 2 adds group tables without changing revision 1 payment tables. Clear the browser cookie and you lose access to that identity; there is no account recovery. Catalog dates are fixed when first seeded and never moved by restarting. Do not reset/delete the database to recover an uncertain payment.

Run the automated checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Hosted judge demos must use managed PostgreSQL and HTTPS, as documented in [STORAGE_HOSTING.md](docs/STORAGE_HOSTING.md). Production SQLite is rejected by the application. No hosted environment or PostgreSQL integration test has been completed in this slice.
