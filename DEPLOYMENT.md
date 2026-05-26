# Aspora Compliance OS — Deployment guide

## TL;DR

```
APP_SECRET=<32+ char random string>      # required in prod; auto-generated for local dev
COMPLIANCE_DB_URL=postgresql+psycopg2://user:pass@host:5432/dbname
COMPLIANCE_BASE_URL=https://aspora-compliance.example.com
COMPLIANCE_AGENT_LIVE=1                  # only if you want Claude features
ANTHROPIC_API_KEY=sk-ant-…               # only if COMPLIANCE_AGENT_LIVE=1

# Optional — email-based password reset:
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=…
SMTP_FROM="Aspora Compliance <no-reply@aspora.com>"

# Optional tuning:
COMPLIANCE_DB_POOL_SIZE=5
COMPLIANCE_DB_MAX_OVERFLOW=5
COMPLIANCE_AUDIT_RETENTION_DAYS=365      # min 30; admin UI surfaces this
COMPLIANCE_UPLOADS_DIR=/var/lib/aspora/uploads
```

## Database

### SQLite (default — fine for single-machine demos)

Nothing to configure. A `compliance.db` file is created in the working
directory. Override the path via `COMPLIANCE_DB_PATH`.

### Postgres

1. Install the Postgres extras:
   ```
   pip install -e ".[postgres]"
   ```
2. Set the connection URL — either form works:
   ```
   COMPLIANCE_DB_URL=postgres://user:pass@host:5432/dbname
   COMPLIANCE_DB_URL=postgresql+psycopg2://user:pass@host:5432/dbname
   ```
   The app rewrites the `postgres://` scheme that Render / Heroku hand out.
3. Tune the pool if needed:
   ```
   COMPLIANCE_DB_POOL_SIZE=10
   COMPLIANCE_DB_MAX_OVERFLOW=10
   ```
4. The boot sequence runs `Base.metadata.create_all()` plus an idempotent
   `ALTER TABLE ADD COLUMN IF NOT EXISTS` sweep for the columns added after
   the initial release. Alembic migrations replace this in the next round.

### Migrating SQLite → Postgres

For a one-time switchover (workspace data is small):

```bash
# 1. Dump the SQLite tables to CSV via your favourite tool.
# 2. Create the Postgres database and let the app boot to create the schema:
COMPLIANCE_DB_URL=postgresql+psycopg2://... python -m compliance_agent.cli seed
# 3. Truncate the demo data and load the CSVs with \copy.
```

## Sessions

JWT sliding refresh is built in. The session cookie has a 7-day TTL; on every
authenticated request older than 3 days, the server mints a fresh token and
replaces the cookie. Daily-active users get perpetual sessions; idle users
expire on schedule.

Set `APP_SECRET` in prod — otherwise the app generates one in `.app_secret`
(which would invalidate everyone's sessions on restart). Use 32+ random chars.

## Rate limits

In-memory, per-user (or per-IP for anonymous). Defaults:

| Endpoint                                | Limit            |
|-----------------------------------------|------------------|
| `POST /api/auth/login`                  | 10 / min         |
| `POST /api/auth/forgot-password`        | 5 / min          |
| `POST /api/auth/reset-password`         | 10 / min         |
| `POST /api/ai/extract-from-document/*`  | 30 / min         |
| `POST /api/ai/second-opinion/*`         | 30 / min         |
| `POST /api/ai/check-rule-changes/*`     | 20 / min         |
| (everything else)                       | 300 / min        |

If we scale horizontally, swap the in-memory store for Redis by setting
`Limiter(storage_uri="redis://…")` in `rate_limit.py`.

## Password reset

Set the `SMTP_*` env vars and the **Forgot password?** link on the sign-in
page just works. Without SMTP, the backend logs the reset URL to the server
console AND the response also carries `dev_reset_url` so the dev who clicked
the link can copy/paste it.

`COMPLIANCE_BASE_URL` controls the link domain (defaults to
`http://127.0.0.1:8000`).

Tokens are SHA-256 hashed in the DB; the raw token is only ever surfaced via
the email link. TTL is 1 hour. Reset succeeds → all other outstanding tokens
for that user are invalidated.

## Audit log retention

`COMPLIANCE_AUDIT_RETENTION_DAYS` (min 30, default 365) sets the window.

Admin → **Settings → Audit retention** shows the current window, total
events, and "older than window" count, with a guarded **Purge** button. The
purge logs itself so the audit feed isn't suspiciously empty after.

There's no scheduled background purge — admins trigger it deliberately.

## Document storage

Local filesystem by default. Set `COMPLIANCE_UPLOADS_DIR` to point at a
persistent volume on the host (e.g. a Render disk mount).

S3/R2 backend is planned for the next round; the `compliance_agent.storage`
module is already shaped as a pluggable contract.
