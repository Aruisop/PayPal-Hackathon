# refactor(app): introduce Flask factory and feature blueprints

## Problem and resulting behavior

This PR refactors the Flask application from a root-level `server.py` layout into a feature-oriented `app/` package, without intentionally changing the existing HTTP, payment, recommendation, or booking behavior.

The application now starts through `python -m app`.

## Delivered scope

- Added Flask application factory: `app.factory.create_app`.
- Split HTTP routes into Flask Blueprints:
  - `app.web.routes`
  - `app.groups.routes`
  - `app.workshops.routes`
- Moved domain services into explicit feature packages:
  - `app/bookings`
  - `app/groups`
  - `app/workshops`
  - `app/planning`
  - `app/recommendations`
  - `app/payments`
  - `app/tickets`
  - `app/shared`
- Centralized configuration, dependency wiring, request guards, security headers, and error handlers in the application factory.
- Replaced root `server.py` with package CLI commands:

  ```bash
  python -m app serve
  python -m app migrate
  python -m app recover
  ```

- Added architecture conventions documentation.

## Scope boundaries

This is an architecture/refactor PR. It does not introduce a new payment flow, alter server-owned pricing or inventory, modify consent rules, or rewrite database migration history.

Existing payment, identity, AI, inventory, and booking safeguards remain in place under their relocated service modules.

## Validation and evidence

- `git diff --check` passed.
- Imports and routes were updated to use the new package structure.

Run before merge:

```bash
python -m unittest discover -s tests -v
python -m pip check
node tests/test_frontend_contract.cjs
node tests/test_demo_contract.cjs
node tests/test_ai_contract.cjs
```

Automated PayPal and AI tests use mocks. They do not establish live PayPal, browser-rendering, or PostgreSQL evidence.

## Integration and limitations

- No credentials, `.env` files, databases, or generated artifacts are included.
- Local development remains SQLite-only.
- Production still requires managed PostgreSQL, HTTPS, and secure cookies.
- This remains a review candidate; merge and deployment are separate decisions.
