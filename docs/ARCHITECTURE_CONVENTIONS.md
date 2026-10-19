# Architecture conventions

Default for new code: a **modular monolith**—one Flask application and database,
organized by feature. Do not add microservices without a proven need.

```text
app/
  shared/              # config, DB, auth, errors only
  groups/              # api.py, service.py, repository.py
  planning/            # api.py, service.py, repository.py
  bookings/            # api.py, service.py, repository.py, suppliers.py
  payments/            # api.py, service.py, repository.py, paypal_client.py
  tickets/             # api.py, service.py, repository.py
  recommendations/     # api.py, service.py, semantic.py
  web/                 # browser assets
tests/
docs/
```

Migrate the current root modules gradually. Do not rewrite correct payment or
migration code only to move files.

## Layer rule

```text
Browser -> API -> Service -> Repository / external adapter
```

- **API**: HTTP input/output and access checks only.
- **Service**: business workflow and state transitions.
- **Repository**: SQL only.
- **Adapter**: PayPal, supplier, or AI calls only.
- A feature does not write another feature's tables directly; call its service.

## Required rules

- Server owns price, currency, quote, inventory and deadlines.
- Use integer cents and UTC timestamps.
- Persist state/operation IDs before retryable provider calls; reconcile before retry.
- Never hold a database transaction across PayPal or supplier calls.
- Only verified completed captures plus verified fulfillment may issue tickets.
- Applied migrations are immutable; add a new migration.
- Simulations never change real payments, inventory, consent or tickets.
- Keep secrets, cookies, databases and generated files out of Git.

## Coding and delivery

- Python uses `snake_case`; classes use `PascalCase`.
- Name by intent: `freeze_roster`, `authorize_contribution`; avoid `process`.
- Add focused service tests. For payments, identity, inventory or recovery also
  test retries, duplicates, restart recovery and unauthorized access.
- One branch/PR per outcome. Use commits such as `feat(groups): freeze roster`.
- A release is ready only when mocks, browser checks, required Sandbox evidence,
  PostgreSQL hosting checks and documentation all agree.
