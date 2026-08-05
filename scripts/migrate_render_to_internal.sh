#!/usr/bin/env bash
#
# One-shot Postgres → Postgres migration for the Render → internal-platform move.
#
# Wraps the whole of MIGRATION.md Step 3a in a single command, with the checks
# that catch the ways this usually goes wrong: a pg_dump older than the server,
# a target that already has rows in it, and a "success" that was never verified.
#
#   export SOURCE_DB_URL='postgresql://…render-external…?sslmode=require'
#   export TARGET_DB_URL='postgresql://…internal…'
#   ./scripts/migrate_render_to_internal.sh
#
# Options:
#   --dry-run     inspect both sides and stop; writes nothing
#   --truncate    wipe the target first (IRREVERSIBLE) — for re-running after
#                 the app booted against the target and auto-created an admin
#   --keep-going  restore even if the target is non-empty (may collide)
#
# The source is only ever read. Nothing is deleted anywhere unless you pass
# --truncate. The dump file is kept as a point-in-time backup.
set -euo pipefail

DRY_RUN=0
TRUNCATE=0
KEEP_GOING=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)    DRY_RUN=1 ;;
    --truncate)   TRUNCATE=1 ;;
    --keep-going) KEEP_GOING=1 ;;
    -h|--help)    sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; BLD=$'\033[1m'; RST=$'\033[0m'
say()  { printf '%s\n' "$*"; }
ok()   { printf '%s✓%s %s\n' "$GRN" "$RST" "$*"; }
warn() { printf '%s!%s %s\n' "$YEL" "$RST" "$*"; }
die()  { printf '%s✗ %s%s\n' "$RED" "$*" "$RST" >&2; exit 1; }
step() { printf '\n%s== %s ==%s\n' "$BLD" "$*" "$RST"; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Host+database only — never echo credentials into a terminal or CI log.
redact() { sed -E 's#://[^@/]*@#://***@#' <<<"$1"; }

# --- Preflight ---------------------------------------------------------------
step "Preflight"

: "${SOURCE_DB_URL:?set SOURCE_DB_URL (Render EXTERNAL url, usually needs ?sslmode=require)}"
: "${TARGET_DB_URL:?set TARGET_DB_URL (the new internal Postgres)}"

for bin in pg_dump pg_restore psql; do
  command -v "$bin" >/dev/null || die "$bin not found. Install the Postgres client tools (e.g. apt install postgresql-client-16)."
done

[[ "$SOURCE_DB_URL" == *sslmode=* ]] || warn "SOURCE_DB_URL has no sslmode — Render's external connections normally need ?sslmode=require"

say "source: $(redact "$SOURCE_DB_URL")"
say "target: $(redact "$TARGET_DB_URL")"

# Reachability, and the server version we must not be older than.
SRC_FULL="$(psql "$SOURCE_DB_URL" -tAc 'SHOW server_version;' 2>/dev/null)" \
  || die "cannot connect to the SOURCE database. Use Render's EXTERNAL url and check ?sslmode=require."
psql "$TARGET_DB_URL" -tAc 'SELECT 1;' >/dev/null 2>&1 \
  || die "cannot connect to the TARGET database."
ok "both databases reachable"

SRC_MAJOR="${SRC_FULL%%.*}"
DUMP_MAJOR="$(pg_dump --version | grep -oE '[0-9]+' | head -1)"
say "server major: $SRC_MAJOR   pg_dump major: $DUMP_MAJOR"
if (( DUMP_MAJOR < SRC_MAJOR )); then
  die "pg_dump ($DUMP_MAJOR) is older than the server ($SRC_MAJOR) and will refuse.
  Run the dump from a matching client instead, e.g.:
    docker run --rm -v \"\$PWD:/out\" postgres:$SRC_MAJOR \\
      pg_dump -Fc --no-owner --no-acl -d \"\$SOURCE_DB_URL\" -f /out/compliance.dump"
fi
ok "pg_dump is new enough"

# --- What's on each side -----------------------------------------------------
step "Current contents"

count_rows() {  # $1=url  → "table rows" lines for the app's core tables, or nothing
  psql "$1" -tA -F' ' -c "
    SELECT 'entities', count(*) FROM entities
    UNION ALL SELECT 'rules', count(*) FROM rules
    UNION ALL SELECT 'obligations', count(*) FROM obligations
    UNION ALL SELECT 'licenses', count(*) FROM licenses
    UNION ALL SELECT 'users', count(*) FROM users
    UNION ALL SELECT 'file_blobs', count(*) FROM file_blobs
    UNION ALL SELECT 'activities', count(*) FROM activities;" 2>/dev/null || true
}

SRC_COUNTS="$(count_rows "$SOURCE_DB_URL")"
[[ -n "$SRC_COUNTS" ]] || die "the SOURCE has no app tables — wrong database? (expected entities/rules/obligations)"
say "SOURCE:"; say "$SRC_COUNTS" | sed 's/^/    /'

SRC_TOTAL="$(awk '{s+=$2} END{print s+0}' <<<"$SRC_COUNTS")"
(( SRC_TOTAL > 0 )) || die "the SOURCE is empty (0 rows across every table). Check you are pointing at the database that holds your data — see MIGRATION.md Step 0."

TGT_COUNTS="$(count_rows "$TARGET_DB_URL")"
if [[ -n "$TGT_COUNTS" ]]; then
  say "TARGET:"; say "$TGT_COUNTS" | sed 's/^/    /'
  TGT_TOTAL="$(awk '{s+=$2} END{print s+0}' <<<"$TGT_COUNTS")"
else
  say "TARGET: no app tables yet (empty database — expected)"
  TGT_TOTAL=0
fi

if (( DRY_RUN )); then
  step "Dry run — nothing written"
  say "Re-run without --dry-run to migrate."
  exit 0
fi

if (( TGT_TOTAL > 0 )); then
  if (( TRUNCATE )); then
    warn "target holds $TGT_TOTAL row(s) — dropping its public schema as requested"
    psql "$TARGET_DB_URL" -v ON_ERROR_STOP=1 -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;' >/dev/null
    ok "target emptied"
  elif (( KEEP_GOING )); then
    warn "target holds $TGT_TOTAL row(s) — continuing anyway (--keep-going); primary keys may collide"
  else
    die "the TARGET already holds $TGT_TOTAL row(s).
  Most likely the app booted against it and auto-created a bootstrap admin.
  Re-run with --truncate to wipe it first, or --keep-going to restore anyway."
  fi
fi

# --- Dump --------------------------------------------------------------------
step "Dump"

STAMP="$(date +%Y%m%d-%H%M%S)"
DUMP="compliance-${STAMP}.dump"
pg_dump -Fc --no-owner --no-acl -d "$SOURCE_DB_URL" -f "$DUMP"
ok "wrote $DUMP ($(du -h "$DUMP" | cut -f1)) — keep this, it is a point-in-time backup"

# --- Restore -----------------------------------------------------------------
step "Restore"

# pg_restore returns non-zero for benign notices too, so capture and inspect.
RESTORE_LOG="restore-${STAMP}.log"
if pg_restore --no-owner --no-acl -d "$TARGET_DB_URL" "$DUMP" >"$RESTORE_LOG" 2>&1; then
  ok "restored cleanly"
else
  warn "pg_restore reported issues — see $RESTORE_LOG (the verification below is what decides)"
  tail -n 15 "$RESTORE_LOG" | sed 's/^/    /'
fi

# --- Verify ------------------------------------------------------------------
step "Verify"

VERIFIED=0
if command -v python3 >/dev/null && python3 -c 'import sqlalchemy' 2>/dev/null; then
  if SOURCE_DB_URL="$SOURCE_DB_URL" TARGET_DB_URL="$TARGET_DB_URL" \
       python3 "$REPO_ROOT/scripts/migrate_data.py" --verify-only; then
    VERIFIED=1
  fi
else
  warn "python3 + sqlalchemy not available, so the per-table check was skipped."
  warn "Install them (pip install -e \".[postgres]\") and run:"
  warn "  python3 scripts/migrate_data.py --verify-only"
  say ""
  say "Falling back to a row-count comparison of the core tables:"
  NEW_COUNTS="$(count_rows "$TARGET_DB_URL")"
  if [[ "$NEW_COUNTS" == "$SRC_COUNTS" ]]; then
    ok "core table counts match"
    VERIFIED=1
  else
    say "SOURCE:"; say "$SRC_COUNTS" | sed 's/^/    /'
    say "TARGET:"; say "$NEW_COUNTS" | sed 's/^/    /'
  fi
fi

step "Result"
if (( VERIFIED )); then
  ok "Migration complete and verified."
  cat <<EOF

Next (MIGRATION.md Steps 4-7):
  1. Set COMPLIANCE_DB_URL on the new platform to the target database.
  2. Copy the env vars — APP_SECRET unchanged, or everyone is logged out.
     Set COMPLIANCE_DB_STRICT=1 so a DB outage fails loudly instead of
     silently falling back to an empty SQLite file.
  3. Add https://NEW_HOST/api/auth/google/callback to the Google OAuth client.
  4. Re-point the Slack interactivity URL and the three /api/cron/* schedules.
  5. Smoke test: log in, open an entity, download an uploaded document,
     then assign a filing (that exercises a write).
  6. Keep Render alive read-only for ~2 weeks as the rollback.

Kept: $DUMP
EOF
else
  die "VERIFICATION FAILED — do not cut over. The source is untouched; investigate,
  then re-run with --truncate once the cause is understood."
fi
