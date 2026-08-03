# Migration runbook — Render → Aspora internal platform

Moving the Compliance AI Agent off Render. Everything user-created lives in the
**database** — including uploaded files, which are rows in `file_blobs`, not
files on disk (Render's filesystem is ephemeral, so the app was deliberately
built that way). There is **no separate file copy step**.

Four things move:

| # | What | How |
|---|---|---|
| 1 | Database (entities, rules, obligations, users, audit log, uploads, integration config) | `scripts/migrate_data.py` |
| 2 | Environment variables / secrets | copy by hand (inventory below) |
| 3 | Public URL settings | `COMPLIANCE_BASE_URL`, `COMPLIANCE_FRONTEND_URL`, CORS, cookie domain |
| 4 | Inbound webhook + cron | re-point Slack interactivity / the schedule at the new domain |

---

## Step 0 — Find out where the data actually is ⚠️

**Do this first; it decides what you migrate.** `db/base.py` falls back to a
local SQLite file when the configured Postgres is unreachable (Render's free
Postgres expires after 90 days). If that ever happened, the live data is in the
SQLite file on the Render disk, **not** in Postgres.

1. Render → service → **Environment**: is `COMPLIANCE_DB_URL` set?
2. Render → **Logs**, at the last boot. A fallback logs a warning about Postgres
   being unreachable and names the SQLite path it fell back to.
3. Confirm with row counts against whichever you believe is live:

```bash
python scripts/migrate_data.py --source "$RENDER_DB_URL" --dry-run
```

The totals must look like your real data (entities, rules, obligations you
recognise). If Postgres comes back nearly empty but the app is full of data, you
are looking at the wrong source — the truth is the SQLite file.

> If the source is the SQLite file, download it off Render first
> (`/api/admin/backup` if enabled, or a shell copy) and pass the local path:
> `--source ./compliance.db`.

---

## Step 1 — Provision the target

Create an empty Postgres database on the internal platform. Note its
connection string; the script accepts `postgres://`, `postgresql://`, or a
SQLite path and normalises it.

**Do not boot the app against it yet.** First boot on an empty database creates
a bootstrap admin user (`_auto_seed_if_empty`), whose ids then collide with the
migrated rows. Either migrate before the first boot, or set
`COMPLIANCE_AUTO_SEED=0` there until the data is in.

Install the Postgres driver wherever you run the script:

```bash
pip install -e ".[postgres]"
```

---

## Step 2 — Freeze writes

Tell the team to stop using the app (a few minutes is enough). Any filing
approved on Render *after* the dump is taken will be lost. If you must be
strict, scale the Render service to zero after the dump.

---

## Step 3 — Migrate

Keep credentials out of your shell history by exporting them first:

```bash
export SOURCE_DB_URL="postgres://…render…"      # or ./compliance.db
export TARGET_DB_URL="postgres://…internal…"

python scripts/migrate_data.py --dry-run          # what's there
python scripts/migrate_data.py                    # do it
```

The script creates the schema on the target, copies every table in
foreign-key-safe order **preserving primary keys**, re-syncs Postgres sequences,
then prints a per-table source-vs-target report and **exits non-zero on any
mismatch**.

It refuses to write into a non-empty target. If the app already booted there and
created an admin row, wipe and redo:

```bash
python scripts/migrate_data.py --truncate         # IRREVERSIBLE
```

Re-check any time, without writing:

```bash
python scripts/migrate_data.py --verify-only
```

**Do not continue unless the report ends in `✅ Migration complete and
verified.`**

---

## Step 4 — Configure the new platform

Point the app at the new database and copy the environment. Only the vars you
actually use need to move; secrets are marked 🔑.

**Database**
- `COMPLIANCE_DB_URL` → the new Postgres URL
- `COMPLIANCE_DB_POOL_SIZE`, `COMPLIANCE_DB_MAX_OVERFLOW`, `COMPLIANCE_DB_CONNECT_TIMEOUT` (optional tuning)
- `COMPLIANCE_DB_STRICT=1` — **recommended on the new platform**: fail loudly instead of silently falling back to SQLite, which is what made Step 0 necessary

**URLs / cookies** (must change with the domain)
- `COMPLIANCE_BASE_URL` → new public API URL
- `COMPLIANCE_FRONTEND_URL` → new SPA URL (only if split-origin)
- `COMPLIANCE_CORS_ORIGINS`, `COMPLIANCE_COOKIE_DOMAIN`, `COMPLIANCE_COOKIE_SECURE`, `COMPLIANCE_COOKIE_SAMESITE`
- `APP_SECRET` 🔑 — **copy as-is**; changing it invalidates every session and password-reset token

**AI**
- `ANTHROPIC_API_KEY` 🔑 / `OPENROUTER_API_KEY` 🔑
- `COMPLIANCE_AGENT_LIVE=1`, `COMPLIANCE_AGENT_FINANCE_ONLY` (keep default on)

**Google (Gmail + Calendar — same OAuth client)**
- `GMAIL_CLIENT_ID` 🔑, `GMAIL_CLIENT_SECRET` 🔑, `GMAIL_REFRESH_TOKEN` 🔑, `GMAIL_SENDER`
- `GOOGLE_CALENDAR_ID` — same calendar; events and their links migrate with `calendar_events`
- `GOOGLE_CLIENT_ID` 🔑 / `GOOGLE_CLIENT_SECRET` 🔑 / `GOOGLE_ALLOWED_DOMAINS` (Google sign-in) — **add the new domain's callback to the OAuth client's authorised redirect URIs in Google Cloud Console**

**Slack**
- `SLACK_SIGNING_SECRET` 🔑 (verifies inbound interactivity)
- Webhook URLs + per-team routing live **in the database** (`workspace_settings`), so they migrate automatically — nothing to re-enter

**Email fallbacks** (whichever you use)
- `SMTP_*`, or `RESEND_API_KEY` 🔑 / `RESEND_FROM`, or `BREVO_API_KEY` 🔑 / `BREVO_FROM` / `BREVO_FROM_NAME`

**Other**
- `CRON_TOKEN` 🔑 (guards the cron endpoints), `REMINDERS_AUTOSEND` (in-app reminder scheduler), `COMPLIANCE_AUDIT_RETENTION_DAYS`, `LOG_LEVEL`
- `COMPLIANCE_AUTO_SEED=0` while cutting over; you can drop it afterwards

---

## Step 5 — Re-point the inbound webhook and cron

Outbound integrations (Slack posts, Gmail, Calendar pushes) work the moment the
env vars are in place. Anything that calls **into** the app is pinned to the old
Render URL and must be updated:

| Integration | New endpoint | Where to change it |
|---|---|---|
| Slack interactivity (buttons) | `POST https://NEW_HOST/api/webhooks/slack/interactivity` | Slack app → Interactivity & Shortcuts → Request URL |
| Reminders cron | `https://NEW_HOST/api/cron/send-reminders?token=$CRON_TOKEN` | the internal platform's scheduler |
| Weekly digest cron | `https://NEW_HOST/api/cron/weekly-digest?token=$CRON_TOKEN` | the internal platform's scheduler |
| Rule sync cron | `https://NEW_HOST/api/cron/sync-rules?token=$CRON_TOKEN` | the internal platform's scheduler |
| Google sign-in redirect | new callback URL | Google Cloud Console → OAuth client |

> The app also runs reminders itself on boot (every 6h) when
> `REMINDERS_AUTOSEND` is enabled, so the reminders cron is a belt-and-braces
> external trigger rather than the only path.

---

## Step 6 — Smoke test on the new platform

1. **Log in** with an existing account (proves `users` + `APP_SECRET` moved).
2. **Dashboard + Calendar** show the expected counts and deadlines.
3. **Open an entity** → Compliance tab lists its rules; **Review & Assign**
   counts match what you had.
4. **Download an uploaded document / licence** — proves `file_blobs` came over.
5. **Audit Log** shows the full history (~all pre-migration events).
6. **Write test**: assign a filing. Confirm it saves, appears on the calendar,
   and pings Slack. This is also the real sequence test — a save that fails with
   a duplicate-key error means sequences weren't re-synced (re-run the script's
   verification).
7. **Webhook test**: use a status button on a Slack card → the obligation's
   status changes in the app (proves `SLACK_SIGNING_SECRET` + the new
   interactivity URL).

---

## Step 7 — Cut over and keep a rollback

- Point DNS / the internal platform's route at the new service.
- **Keep the Render service and its database alive, read-only, for ~2 weeks.**
  That is your rollback: if something is wrong, point DNS back.
- Re-run `--verify-only` once more after cutover for a clean record.
- Only after the grace period: delete the Render service, then the Render
  database.

### Rollback

Nothing about the migration mutates the source, so rolling back is just
re-pointing DNS at Render and restoring `COMPLIANCE_DB_URL` there. Any work done
on the new platform after cutover would need re-doing — which is why the grace
period is short and the smoke test happens before DNS moves.

---

## Notes on the script

`scripts/migrate_data.py` drives SQLAlchemy off the app's own models, so it
stays correct as the schema changes and works for every engine pairing
(SQLite→Postgres, Postgres→Postgres, and back).

Verified end-to-end against a real Postgres 16 instance: SQLite→Postgres,
Postgres→Postgres, and SQLite→SQLite, with row-level equality on every column
(binary blobs by SHA-256, nested JSON, unicode, enum members), zero FK orphans,
correct sequence re-sync (the next insert continues past migrated ids), and the
app booting against the migrated database without the auto-seed creating a
duplicate admin.

```
--dry-run          inspect the source; writes nothing
--verify-only      compare source vs target; writes nothing
--truncate         wipe the target first (irreversible)
--allow-nonempty   insert into a non-empty target (resuming a failed run)
--tables a,b       copy a subset
--batch-size N     rows per insert (default 500)
```

Passwords are redacted from all output, so logs are safe to paste.
