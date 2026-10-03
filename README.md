# PayPal Sandbox checkout demo

A local payment demo for a fixed **$25.00 USD** product, using a Python server and PayPal's browser SDK. It supports server-side order creation and capture, a forced decline scenario, and a separate simulated checkout.

Start with the [coworker development guide](docs/DEVELOPMENT_GUIDE.md) for setup, architecture, current verification status, troubleshooting, and development pitfalls. The [Sandbox setup guide](README_setup_guide.md) contains the longer account and API walkthrough.

Requires Python 3.10+; no packages need to be installed.

```powershell
# First setup only; do not overwrite an existing .env.
Copy-Item .env.example .env
# Add Sandbox app credentials to .env, then:
python server.py
```

Open http://localhost:8000. Without credentials, use **Try simulated checkout**. For actual Sandbox checkout, use a **US Personal buyer account** with the current **IN Business seller account**. Keep credentials private and never commit `.env`.

Run the automated checks:

```powershell
python -m unittest discover -s tests -v
```
