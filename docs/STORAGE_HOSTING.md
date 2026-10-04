# Storage decision for the workshop purchase slice

Implementation decision, before selecting the database layer: local development uses an ignored SQLite file in `instance/`. The hosted judge demo uses a separately provisioned **managed PostgreSQL database**, never SQLite on a web service's ephemeral filesystem.

The application will use SQLAlchemy Core with the same versioned schema/migration command for both databases. `DATABASE_URL` selects the database; local setup requires no Docker. SQLite-only connection settings will be conditional. Booking uniqueness, payment-operation claims, sessions, request IDs and entitlements live in the database, not the web process.

For a hosted judge demo:

1. Provision a paid managed Render Postgres instance (or another managed PostgreSQL service with equivalent persistence). Do not depend on an expiring free database for the judging period.
2. Set the web service's `DATABASE_URL` to the managed connection URL; use the provider's required TLS configuration for external connections. A Render web service and database in the same region may use its internal connection URL.
3. Set `APP_ENV=production`, `APP_ORIGIN` to the exact HTTPS demo origin, `COOKIE_SECURE=true`, and PayPal Sandbox app credentials as private environment variables. `PAYPAL_MERCHANT_ID` is an optional expected-seller validation pin; single-merchant Standard Checkout needs only the app Client ID and Secret.
4. Install pinned dependencies, run `python server.py migrate` once as the deployment migration step, then start the application through Waitress. The web service refuses production SQLite and a non-HTTPS origin.
5. Keep database lifecycle separate from web deployments. Configure backups/recovery and retain the database through judging. Restarting/redeploying the web process must preserve session identities, bookings, attempts and access.

No hosted resources are created by this slice. Managed PostgreSQL execution must be verified before claiming a hosted demo; local SQLite tests are not PostgreSQL integration evidence. Schema changes require a new explicit migration, not editing an already applied revision. No database transaction may span a PayPal request.

Sources: [Render Postgres provisioning](https://render.com/docs/postgresql-creating-connecting), [Render free-service limitations](https://render.com/docs/free), [SQLAlchemy database URLs](https://docs.sqlalchemy.org/en/20/core/engines.html).
