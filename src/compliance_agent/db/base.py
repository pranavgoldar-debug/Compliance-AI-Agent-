"""SQLAlchemy engine, session factory, and Base.

Connection URL precedence:
  1. COMPLIANCE_DB_URL — full SQLAlchemy URL.
       SQLite:    sqlite:///./compliance.db
       Postgres:  postgresql+psycopg2://user:pass@host:5432/dbname
  2. COMPLIANCE_DB_PATH — file path for SQLite. Default: ./compliance.db

For Postgres you also need `pip install -e ".[postgres]"` to pull psycopg2.
The schema is still created via Base.metadata.create_all on boot; switch to
Alembic when we cut the next round of schema changes.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def _resolve_url() -> str:
    url = os.environ.get("COMPLIANCE_DB_URL")
    if url:
        # Heroku / Render hand out `postgres://`; SQLAlchemy 2.x needs the
        # explicit driver form.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://"):]
        return url
    db_path = Path(os.environ.get("COMPLIANCE_DB_PATH", "compliance.db")).resolve()
    return f"sqlite:///{db_path}"


DATABASE_URL = _resolve_url()


def _engine_kwargs(url: str) -> dict:
    """Build per-backend SQLAlchemy engine kwargs."""
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        # check_same_thread=False is safe because we use a session-per-request
        # pattern and never share a Session across threads.
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Sensible defaults for Postgres on a single-instance Render dyno;
        # tune up when we scale horizontally.
        kwargs["pool_size"] = int(os.environ.get("COMPLIANCE_DB_POOL_SIZE", "5"))
        kwargs["max_overflow"] = int(os.environ.get("COMPLIANCE_DB_MAX_OVERFLOW", "5"))
        kwargs["pool_recycle"] = 1800
    return kwargs


engine = create_engine(DATABASE_URL, **_engine_kwargs(DATABASE_URL))

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create all tables. Idempotent. Safe to call on every boot.

    Also runs a tiny ad-hoc migration for SQLite to add columns we add
    after the initial release — full Alembic comes later. On Render's
    free tier where the Shell isn't available, also auto-seeds the
    database the very first time it boots empty.
    """
    # Import here so the model module is registered before create_all.
    from compliance_agent.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    _migrate_obligation_unique()
    _auto_seed_if_empty()


def _migrate_obligation_unique() -> None:
    """Replace the pre-PR-B `(rule_id, entity_id, due_date)` unique constraint
    with the post-PR-B `(rule_id, entity_id, due_date, department)` version.

    `Base.metadata.create_all` only creates tables that don't exist — it
    won't ALTER existing constraints. SQLite and Postgres both handle
    `DROP INDEX IF EXISTS` + `CREATE UNIQUE INDEX` cleanly, so we do the
    swap here. Idempotent: skips both steps when the new index is already
    present.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "obligations" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("obligations")}
    if "department" not in cols:
        # Column hasn't been added yet (will run again on next boot).
        return

    indexes = inspector.get_indexes("obligations")
    have_old = any(i["name"] == "uq_obligation_rule_entity_date" for i in indexes)
    have_new = any(i["name"] == "uq_obligation_rule_entity_date_dept" for i in indexes)
    if have_new and not have_old:
        return

    with engine.begin() as conn:
        if have_old:
            conn.execute(text("DROP INDEX IF EXISTS uq_obligation_rule_entity_date"))
        if not have_new:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "uq_obligation_rule_entity_date_dept "
                    "ON obligations (rule_id, entity_id, due_date, department)"
                )
            )


# Re-entry guard. run_seed() itself calls init_db(), so without this the
# auto-seed would call run_seed which would call init_db which would call
# auto-seed which would call run_seed ... → RecursionError.
_AUTO_SEED_RUNNING = False


def _auto_seed_if_empty() -> None:
    """First-boot bootstrap. If the users table is empty, run the demo seed
    so logins work without anyone having to SSH in. After that, this is a
    one-query no-op on every restart.

    Can be disabled by setting COMPLIANCE_AUTO_SEED=0 in the environment —
    useful if you're about to import production data and don't want demo
    rows in the way.
    """
    global _AUTO_SEED_RUNNING
    if _AUTO_SEED_RUNNING:
        return
    if os.environ.get("COMPLIANCE_AUTO_SEED") == "0":
        return
    from sqlalchemy import func, select

    from compliance_agent.db.models import User

    with SessionLocal() as session:
        try:
            n = session.execute(select(func.count(User.id))).scalar_one()
        except Exception:  # noqa: BLE001
            # Tables not ready yet (rare race) — skip; next boot will catch it.
            return
        if n and n > 0:
            return

    _AUTO_SEED_RUNNING = True
    try:
        # Lazy import — the seed-only modules aren't needed in steady state.
        from compliance_agent.db.seed import run_seed

        run_seed()
    except Exception as e:  # noqa: BLE001
        # Never block boot on seed failure. Surface in logs so an admin
        # can re-run seed manually if they need to.
        import logging

        logging.getLogger(__name__).warning(
            "Auto-seed skipped due to error: %s", e
        )
    finally:
        _AUTO_SEED_RUNNING = False


def _add_missing_columns() -> None:
    """Add any new columns declared on existing models that aren't yet in
    the live DB, then run any one-shot data fix-ups. Idempotent. Works on
    SQLite and Postgres — both accept ALTER TABLE ADD COLUMN. When we move
    to Alembic (next round) this will be replaced by versioned migrations."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    is_pg = DATABASE_URL.startswith("postgres")
    text_type = "TEXT"
    varchar = lambda n: f"VARCHAR({n})"
    datetime_type = "TIMESTAMP" if is_pg else "DATETIME"

    # SQLAlchemy's SAEnum stores enum NAMES in the DB by default. EffortBand
    # has names like `w4` and values like `4w` — different — so the DEFAULT
    # here MUST be the name.
    bool_default_true = "BOOLEAN NOT NULL DEFAULT 1" if not is_pg else "BOOLEAN NOT NULL DEFAULT TRUE"

    table_additions: dict[str, list[tuple[str, str]]] = {
        # Phase 5: effort bands on obligations.
        # PR-B (department split): every obligation owns by a department.
        "obligations": [
            ("effort_band", f"{varchar(8)} NOT NULL DEFAULT 'w4'"),
            ("effort_band_reason", text_type),
            ("department", f"{varchar(16)} NOT NULL DEFAULT 'compliance'"),
            ("clickup_task_id", varchar(64)),
            ("clickup_task_url", varchar(512)),
        ],
        # Phase 7: source provenance on rules
        "rules": [
            ("source_url", varchar(1024)),
            ("source_text", text_type),
            ("source_changed_at", datetime_type),
        ],
        # Phase 9: per-user notification prefs + Slack member id +
        # functional department (drives finance / compliance routing).
        "users": [
            ("notify_email", bool_default_true),
            ("notify_slack", bool_default_true),
            ("slack_user_id", varchar(64)),
            ("department", varchar(16)),
        ],
        # Tracker sync: short codes for each entity (VINC, RTUK, ...)
        "entities": [
            ("short_code", varchar(32)),
        ],
    }

    # Widen jurisdiction_code VARCHAR(8) → VARCHAR(16) on existing Postgres
    # DBs. The catalog ships codes like "singapore"/"lithuania" (9 chars)
    # which Postgres rejects against the original VARCHAR(8). SQLite doesn't
    # enforce VARCHAR length, so this is Postgres-only. Idempotent: only runs
    # where the column is still narrower than 16.
    if is_pg:
        with engine.begin() as conn:
            for jtable in ("entities", "rules", "licenses"):
                if jtable not in tables:
                    continue
                col = next(
                    (c for c in inspector.get_columns(jtable)
                     if c["name"] == "jurisdiction_code"),
                    None,
                )
                length = getattr(col["type"], "length", None) if col else None
                if length is not None and length < 16:
                    conn.execute(
                        text(
                            f"ALTER TABLE {jtable} "
                            "ALTER COLUMN jurisdiction_code TYPE VARCHAR(16)"
                        )
                    )

    with engine.begin() as conn:
        for table, additions in table_additions.items():
            if table not in tables:
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            for col_name, col_def in additions:
                if col_name in existing:
                    continue
                # Postgres supports IF NOT EXISTS; SQLite doesn't but the
                # existing-cols check above already gates us.
                guard = "IF NOT EXISTS " if is_pg else ""
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {guard}{col_name} {col_def}")
                )

        # One-shot data fix: an earlier release shipped with DEFAULT '4w'
        # (the enum VALUE), but SAEnum reads the NAME. Migrate legacy rows
        # so SAEnum stops choking with `'4w' is not among the defined enum
        # values`. Idempotent — re-runs are no-ops.
        if "obligations" in tables:
            band_value_to_name = {
                "1w": "w1",
                "2w": "w2",
                "4w": "w4",
                "8w": "w8",
                "12w": "w12",
            }
            for bad, good in band_value_to_name.items():
                # CAST the column to TEXT in the WHERE clause: on Postgres the
                # bare literal :bad ('1w', '4w', …) is validated against the
                # effortband ENUM type at plan time and rejected (those are
                # enum VALUES, not NAMES), crashing even when no rows match.
                # Casting to text sidesteps the enum check. No-op on SQLite.
                conn.execute(
                    text(
                        "UPDATE obligations SET effort_band = :good "
                        "WHERE CAST(effort_band AS TEXT) = :bad"
                    ),
                    {"good": good, "bad": bad},
                )

        # tax_type on rules (Direct / Indirect / Not-a-Tax). SAEnum stores the
        # enum NAME, so the DB values are direct / indirect / not_tax. On
        # Postgres the `taxtype` enum type isn't auto-created by create_all when
        # the rules table already exists, so we create it explicitly (idempotent
        # via the duplicate_object guard) before adding the column.
        if "rules" in tables:
            rules_cols = {col["name"] for col in inspector.get_columns("rules")}
            if "tax_type" not in rules_cols:
                if is_pg:
                    conn.execute(
                        text(
                            "DO $$ BEGIN "
                            "CREATE TYPE taxtype AS ENUM "
                            "('direct', 'indirect', 'not_tax'); "
                            "EXCEPTION WHEN duplicate_object THEN null; "
                            "END $$;"
                        )
                    )
                    conn.execute(
                        text(
                            "ALTER TABLE rules ADD COLUMN IF NOT EXISTS tax_type "
                            "taxtype NOT NULL DEFAULT 'not_tax'"
                        )
                    )
                else:
                    conn.execute(
                        text(
                            "ALTER TABLE rules ADD COLUMN tax_type "
                            f"{varchar(16)} NOT NULL DEFAULT 'not_tax'"
                        )
                    )

                # One-shot backfill so the pre-loaded catalog (which was
                # seeded before this column existed) gets sensible defaults
                # without a re-seed. Conservative category match; only touches
                # rows still at the not_tax default, so it never overwrites an
                # admin's manual choice. Stored values are enum NAMES.
                conn.execute(
                    text(
                        "UPDATE rules SET tax_type = 'indirect' "
                        "WHERE tax_type = 'not_tax' AND ("
                        "lower(category) LIKE '%gst%' OR "
                        "lower(category) LIKE '%vat%' OR "
                        "lower(category) LIKE '%sales%tax%' OR "
                        "lower(category) LIKE '%use tax%' OR "
                        "lower(category) LIKE '%excise%' OR "
                        "lower(category) LIKE '%customs%' OR "
                        "lower(category) LIKE '%import duty%' OR "
                        "lower(category) LIKE '%indirect%')"
                    )
                )
                conn.execute(
                    text(
                        "UPDATE rules SET tax_type = 'direct' "
                        "WHERE tax_type = 'not_tax' AND ("
                        "lower(category) LIKE '%corporate tax%' OR "
                        "lower(category) LIKE '%income tax%' OR "
                        "lower(category) LIKE '%corporate income%' OR "
                        "lower(category) LIKE '%capital gains%' OR "
                        "lower(category) LIKE '%direct tax%')"
                    )
                )


def get_session() -> Iterator[Session]:
    """FastAPI dependency — yields a session that auto-closes after the request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Use outside FastAPI (e.g. seed scripts, CLI commands)."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
