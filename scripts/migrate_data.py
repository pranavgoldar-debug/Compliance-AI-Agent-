#!/usr/bin/env python3
"""Copy the ENTIRE Compliance-AI-Agent database from one engine to another.

Built for the Render → Aspora-internal-platform move, but engine-agnostic: it
handles every combination of SQLite and Postgres, because Render's deployment
can legitimately be either one (``COMPLIANCE_DB_URL`` points at Postgres, but
``db/base.py`` silently falls back to a local SQLite file when that Postgres is
unreachable — so the live data may be in either place).

Why a copier and not ``pg_dump``: pg_dump only covers Postgres→Postgres, needs
matching server versions, and can't do the SQLite case at all. This script
drives SQLAlchemy Core off the app's own models, so it works for every pairing
and stays correct as the schema evolves.

What it guarantees
------------------
* **Every table**, copied in foreign-key-safe order (``metadata.sorted_tables``).
* **Primary keys preserved** — ids are copied verbatim, so every foreign key
  (and every ``clickup_task_id`` / calendar-event link) still resolves. Uploaded
  files ride along automatically: they are rows in ``file_blobs``, not files on
  disk.
* **Postgres sequences re-synced** after the copy, so the next insert on the new
  platform doesn't collide with a migrated id.
* **Verified** — row counts and max(id) are compared per table at the end, and
  the script exits non-zero on any mismatch. No silent partial migration.

Usage
-----
    pip install -e ".[postgres]"        # psycopg2, for postgresql:// URLs

    # 1. Look before you leap: what's in the source?
    python scripts/migrate_data.py --source "$SOURCE_DB_URL" --dry-run

    # 2. Real run into the empty target.
    python scripts/migrate_data.py \
        --source "$SOURCE_DB_URL" --target "$TARGET_DB_URL"

    # 3. Re-check an earlier migration without writing anything.
    python scripts/migrate_data.py \
        --source "$SOURCE_DB_URL" --target "$TARGET_DB_URL" --verify-only

URLs may also come from the SOURCE_DB_URL / TARGET_DB_URL environment
variables, which keeps credentials out of your shell history. A SQLite source
is given as a path or a URL: ``./compliance.db`` or ``sqlite:///abs/path.db``.

Safety
------
The target must be EMPTY. If it already holds rows the script stops and tells
you which tables — pass ``--truncate`` to wipe it first (irreversible), or
``--allow-nonempty`` to insert anyway (only sane when resuming a run that died
part-way; duplicate primary keys will error).

This matters because booting the app against a fresh database creates a
bootstrap admin user (``_auto_seed_if_empty``), which then collides with the
migrated ``users`` rows. Migrate BEFORE the app's first boot on the new
platform, or set ``COMPLIANCE_AUTO_SEED=0`` there until the data is in.

The source is only ever read from — this script issues no writes against it.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from typing import Optional

# --- Import the app's models WITHOUT waking its global engine -----------------
# db/base.py resolves a module-level engine at import time (and probes Postgres
# for reachability). We only want the metadata, so point that global at a
# throwaway SQLite path first: create_engine is lazy, so nothing is created and
# nothing is connected. The real source/target engines are built explicitly.
os.environ.pop("COMPLIANCE_DB_URL", None)
os.environ["COMPLIANCE_DB_PATH"] = os.path.join(
    tempfile.gettempdir(), "compliance_migrate_scratch.db"
)
os.environ["COMPLIANCE_AUTO_SEED"] = "0"  # belt-and-braces: never seed from here

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_REPO_ROOT, os.path.join(_REPO_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import create_engine, func, inspect, select, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from compliance_agent.db import Base  # noqa: E402
from compliance_agent.db import models  # noqa: F401,E402  (registers every table)


# Blobs are big; copy them in smaller batches so memory stays flat.
BLOB_TABLES = {"file_blobs"}
BLOB_BATCH = 25


def normalize_url(raw: str) -> str:
    """Accept every shape of URL we might be handed.

    Render/Heroku hand out ``postgres://``, which SQLAlchemy 2.x rejects; a bare
    filesystem path means a SQLite file (the fallback database).
    """
    url = (raw or "").strip()
    if not url:
        raise ValueError("empty database URL")
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]
    elif "://" not in url:
        url = f"sqlite:///{os.path.abspath(os.path.expanduser(url))}"
    return url


def redact(url: str) -> str:
    """Hide the password so the URL is safe to print in logs/CI output."""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        creds, host = rest.rsplit("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return url


def is_postgres(engine: Engine) -> bool:
    return engine.dialect.name.startswith("postgres")


def build_engine(url: str, *, label: str) -> Engine:
    engine = create_engine(url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — a bad URL should read clearly
        raise SystemExit(f"ERROR: cannot connect to {label} ({redact(url)}): {exc}")
    return engine


def table_order() -> list:
    """Tables in FK-safe insert order (parents first). The schema has no
    self-referential or circular FKs, so sorted_tables is a total order."""
    return list(Base.metadata.sorted_tables)


def existing_tables(engine: Engine) -> set:
    return set(inspect(engine).get_table_names())


def count_rows(engine: Engine, table) -> Optional[int]:
    """Row count, or None when the table doesn't exist on this engine."""
    if table.name not in existing_tables(engine):
        return None
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(table)).scalar_one())


def max_pk(engine: Engine, table) -> Optional[int]:
    """max() of a single-column integer PK — a cheap second signal beyond counts."""
    pk_cols = list(table.primary_key.columns)
    if len(pk_cols) != 1:
        return None
    col = pk_cols[0]
    if not isinstance(col.type.python_type, type) or col.type.python_type is not int:
        return None
    if table.name not in existing_tables(engine):
        return None
    with engine.connect() as conn:
        return conn.execute(select(func.max(col))).scalar()


def truncate_target(engine: Engine, tables: list) -> None:
    """Empty every target table, children first so FKs never block the delete."""
    with engine.begin() as conn:
        present = existing_tables(engine)
        if is_postgres(engine):
            names = [f'"{t.name}"' for t in tables if t.name in present]
            if names:
                # One statement: CASCADE + RESTART IDENTITY clears dependents and
                # rewinds sequences in a single pass.
                conn.execute(
                    text(f"TRUNCATE {', '.join(names)} RESTART IDENTITY CASCADE")
                )
        else:
            for table in reversed(tables):
                if table.name in present:
                    conn.execute(table.delete())


def copy_table(src: Engine, dst: Engine, table, *, batch_size: int) -> int:
    """Stream one table across, preserving primary keys. Returns rows copied.

    Reads and writes go through the SAME Column types, so JSON dicts, enum
    members, booleans, datetimes and LargeBinary blobs all round-trip through
    their type's result/bind processors — no manual coercion, and no
    SQLite-vs-Postgres representation drift.
    """
    size = BLOB_BATCH if table.name in BLOB_TABLES else batch_size
    columns = [c.name for c in table.columns]
    copied = 0

    with src.connect() as sconn, dst.begin() as dconn:
        result = sconn.execution_options(stream_results=True).execute(
            table.select().order_by(*table.primary_key.columns)
        )
        while True:
            rows = result.fetchmany(size)
            if not rows:
                break
            dconn.execute(
                table.insert(),
                [dict(zip(columns, row)) for row in rows],
            )
            copied += len(rows)
            print(f"      … {copied} rows", end="\r", flush=True)
    if copied:
        print(" " * 24, end="\r")  # clear the progress line
    return copied


def resync_sequences(engine: Engine, tables: list) -> list:
    """Advance each Postgres identity sequence past the ids we just inserted.

    Without this the next INSERT reuses id 1 and trips a unique-violation, which
    is the classic "migration worked, then the app broke on first write" bug.
    """
    if not is_postgres(engine):
        return []
    touched = []
    with engine.begin() as conn:
        for table in tables:
            pk_cols = list(table.primary_key.columns)
            if len(pk_cols) != 1:
                continue
            col = pk_cols[0]
            seq = conn.execute(
                text("SELECT pg_get_serial_sequence(:t, :c)"),
                {"t": table.name, "c": col.name},
            ).scalar()
            if not seq:
                continue
            top = conn.execute(select(func.max(col))).scalar()
            if top is None:
                continue
            conn.execute(
                text("SELECT setval(CAST(:s AS regclass), CAST(:v AS bigint), true)"),
                {"s": seq, "v": int(top)},
            )
            touched.append(f"{table.name}.{col.name} → {top}")
    return touched


def verify(src: Engine, dst: Engine, tables: list) -> tuple[bool, list]:
    """Compare row counts and max(id) per table. Returns (ok, report rows)."""
    report, ok = [], True
    for table in tables:
        s_count, d_count = count_rows(src, table), count_rows(dst, table)
        s_max, d_max = max_pk(src, table), max_pk(dst, table)
        # A table absent from the source (older DB) with nothing in the target is
        # fine; anything else that differs is a real mismatch.
        if s_count is None:
            match = not d_count
        else:
            match = (s_count == d_count) and (s_max == d_max)
        ok = ok and match
        report.append(
            {
                "table": table.name,
                "source": s_count,
                "target": d_count,
                "source_max_id": s_max,
                "target_max_id": d_max,
                "ok": match,
            }
        )
    return ok, report


def print_report(report: list, *, header: str) -> None:
    print(f"\n{header}")
    print(f"  {'table':<24} {'source':>9} {'target':>9} {'max id':>9}   status")
    print(f"  {'-' * 24} {'-' * 9} {'-' * 9} {'-' * 9}   ------")
    for row in report:
        s = "—" if row["source"] is None else row["source"]
        d = "—" if row["target"] is None else row["target"]
        m = "—" if row["source_max_id"] is None else row["source_max_id"]
        flag = "ok" if row["ok"] else "MISMATCH"
        print(f"  {row['table']:<24} {s:>9} {d:>9} {m:>9}   {flag}")
    total_s = sum(r["source"] or 0 for r in report)
    total_d = sum(r["target"] or 0 for r in report)
    print(f"  {'-' * 24} {'-' * 9} {'-' * 9}")
    print(f"  {'TOTAL':<24} {total_s:>9} {total_d:>9}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate the Compliance-AI-Agent database between engines.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        default=os.environ.get("SOURCE_DB_URL"),
        help="source DB URL or SQLite path (env: SOURCE_DB_URL)",
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("TARGET_DB_URL"),
        help="target DB URL (env: TARGET_DB_URL)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="inspect the source and print what WOULD be copied; touches nothing",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="only compare source vs target (no schema changes, no copying)",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="wipe the target's tables before copying (IRREVERSIBLE)",
    )
    parser.add_argument(
        "--allow-nonempty",
        action="store_true",
        help="insert into a non-empty target instead of refusing (may collide)",
    )
    parser.add_argument("--batch-size", type=int, default=500, help="rows per insert")
    parser.add_argument(
        "--tables",
        default="",
        help="comma-separated subset to copy (default: every table)",
    )
    args = parser.parse_args()

    if not args.source:
        parser.error("--source is required (or set SOURCE_DB_URL)")
    if not args.target and not args.dry_run:
        parser.error("--target is required (or set TARGET_DB_URL) unless --dry-run")

    src_url = normalize_url(args.source)
    src = build_engine(src_url, label="source")
    print(f"source: {redact(src_url)}  [{src.dialect.name}]")

    tables = table_order()
    if args.tables:
        wanted = {t.strip() for t in args.tables.split(",") if t.strip()}
        unknown = wanted - {t.name for t in tables}
        if unknown:
            raise SystemExit(f"ERROR: unknown table(s): {', '.join(sorted(unknown))}")
        tables = [t for t in tables if t.name in wanted]

    # ---- Dry run: report the source and stop --------------------------------
    if args.dry_run:
        print(f"\nDRY RUN — nothing will be written.\n\n  {'table':<24} {'rows':>9}")
        print(f"  {'-' * 24} {'-' * 9}")
        total = 0
        for table in tables:
            n = count_rows(src, table)
            total += n or 0
            print(f"  {table.name:<24} {('—' if n is None else n):>9}")
        print(f"  {'-' * 24} {'-' * 9}\n  {'TOTAL':<24} {total:>9}")
        print("\nRe-run without --dry-run (and with --target) to migrate.")
        return 0

    tgt_url = normalize_url(args.target)
    dst = build_engine(tgt_url, label="target")
    print(f"target: {redact(tgt_url)}  [{dst.dialect.name}]")

    # ---- Verify only: compare and stop -------------------------------------
    if args.verify_only:
        ok, report = verify(src, dst, tables)
        print_report(report, header="VERIFICATION (source vs target)")
        print("\n✅ Verified: source and target match." if ok else "\n❌ MISMATCH — see above.")
        return 0 if ok else 1

    # ---- Schema on the target ----------------------------------------------
    # create_all is idempotent and builds from the CURRENT models, so a fresh
    # target lands on today's schema — the ad-hoc column backfills in
    # db/base.py exist only to upgrade older databases in place.
    print("\ncreating schema on target (idempotent)…")
    Base.metadata.create_all(bind=dst)

    # ---- Guard the target --------------------------------------------------
    occupied = [
        (t.name, n) for t in tables if (n := count_rows(dst, t))
    ]
    if occupied:
        if args.truncate:
            print(f"target is not empty; truncating {len(occupied)} table(s) as asked…")
            truncate_target(dst, tables)
        elif not args.allow_nonempty:
            listing = ", ".join(f"{name} ({n})" for name, n in occupied)
            print(
                f"\nERROR: target already contains rows: {listing}\n"
                "  This usually means the app already booted against it and "
                "auto-created an admin user.\n"
                "  Re-run with --truncate to wipe the target first, or "
                "--allow-nonempty to insert anyway.",
                file=sys.stderr,
            )
            return 2

    # ---- Copy --------------------------------------------------------------
    print(f"\ncopying {len(tables)} table(s)…")
    for table in tables:
        if count_rows(src, table) is None:
            print(f"  · {table.name:<24} skipped (absent from source)")
            continue
        n = copy_table(src, dst, table, batch_size=args.batch_size)
        print(f"  · {table.name:<24} {n} row(s)")

    # ---- Sequences ---------------------------------------------------------
    touched = resync_sequences(dst, tables)
    if touched:
        print(f"\nre-synced {len(touched)} Postgres sequence(s):")
        for line in touched:
            print(f"  · {line}")

    # ---- Verify ------------------------------------------------------------
    ok, report = verify(src, dst, tables)
    print_report(report, header="VERIFICATION (source vs target)")
    if ok:
        print(
            "\n✅ Migration complete and verified.\n"
            "   Next: point COMPLIANCE_DB_URL at the new database, copy the env "
            "vars, then re-register the ClickUp webhook against the new domain.\n"
            "   See MIGRATION.md for the full cutover order."
        )
        return 0
    print("\n❌ MISMATCH — do NOT cut over. Investigate the rows above.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
