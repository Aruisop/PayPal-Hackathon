# Workshop purchase slice

Branch: `slice/1-persistent-workshop-checkout`. Status: **implemented; external architecture acceptance pending**. `master` retains the earlier retail demo. See the [branch map](docs/BRANCHES.md) for delivered scope and future branch conventions, [contributor workflow](CONTRIBUTING.md), and [current development guide](docs/DEVELOPMENT_GUIDE.md). AI contributors should also read [AGENTS.md](AGENTS.md).

A merchant catalog with two scheduled online workshops at **$25.00** and **$18.00 USD**. Each browser profile has its own persistent participant session. A completed, validated PayPal Sandbox capture unlocks only that participant's sample lesson.

This is the first approved workshop slice. Group coordination and AI preferences remain future work. SDK v5 is deliberately retained; v6 migration is separate. Read the [slice review](docs/SLICE1_REVIEW.md) and [durable hosting decision](docs/STORAGE_HOSTING.md). Earlier planning documents are preserved as historical context.

Requires Python 3.10+. No Node.js or Docker is required.

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

Local SQLite data is stored in ignored `instance/workshops.db`; sessions and bookings survive restart. Clear the browser cookie and you lose access to that identity; this slice has no account recovery. Catalog dates are fixed when first seeded and never moved by restarting. Do not reset/delete the database to recover an uncertain payment.

Run the automated checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Hosted judge demos must use managed PostgreSQL and HTTPS, as documented in [STORAGE_HOSTING.md](docs/STORAGE_HOSTING.md). Production SQLite is rejected by the application. No hosted environment or PostgreSQL integration test has been completed in this slice.
