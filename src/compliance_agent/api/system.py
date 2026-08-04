"""System info — small endpoint the UI polls to flip the mode badge."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from compliance_agent.ai.llm_client import active_backend, ai_available
from compliance_agent.auth import require_admin
from compliance_agent.db import User


router = APIRouter(prefix="/api/system", tags=["system"])


class SystemInfo(BaseModel):
    mode: str  # "live" or "mock"
    ai_available: bool
    backend: str  # "anthropic" / "openrouter" / "mock"
    version: str


@router.get("/info", response_model=SystemInfo)
def system_info() -> SystemInfo:
    available = ai_available()
    return SystemInfo(
        mode="live" if available else "mock",
        ai_available=available,
        backend=active_backend(),
        version="0.6.0",
    )


@router.get("/run-reminders")
def run_reminders(dry_run: bool = False, _: User = Depends(require_admin)) -> dict:
    """Admin-only, browser-openable: run the reminder engine RIGHT NOW —
    same as the daily cron. Use `?dry_run=true` to preview what would fire
    without sending anything. Open while logged in as an admin:
    `/api/system/run-reminders`.
    """
    from compliance_agent.reminders import send_reminders

    results = send_reminders(dry_run=dry_run)
    return {
        "ok": True,
        "dry_run": dry_run,
        "fired": [
            {
                "obligation_id": r.obligation_id,
                "assignee": r.assignee_email,
                "days_remaining": r.days_remaining,
                "slot": r.offset_days,
                "email_sent": r.email_sent,
                "slack_sent": r.slack_sent,
            }
            for r in results
        ],
    }


@router.get("/find-rules")
def find_rules(q: str = "", _: User = Depends(require_admin)) -> dict:
    """Admin-only, browser-openable diagnostic: search EVERY rule — all
    statuses, ignoring the Finance-only visibility filter — by name / form /
    authority / jurisdiction, plus the most recent rule-related audit-log
    entries. Use it to trace where a filing went:
    `/api/system/find-rules?q=gpm312`.
    """
    from sqlalchemy import desc, or_, select

    from compliance_agent.db import Activity, Rule, session_scope

    with session_scope() as db:
        stmt = select(Rule)
        if q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    Rule.name.ilike(like),
                    Rule.form_name.ilike(like),
                    Rule.authority.ilike(like),
                    Rule.jurisdiction_code.ilike(like),
                )
            )
        rules = db.execute(stmt.order_by(desc(Rule.updated_at)).limit(100)).scalars().all()
        rules_out = [
            {
                "id": r.id,
                "form_name": r.form_name,
                "name": r.name,
                "jurisdiction": r.jurisdiction_code,
                "status": r.status.value,
                "sent_to_review": bool(r.sent_to_review),
                "responsible_function": r.responsible_function,
                "category": r.category,
                "entities": [e.name for e in r.entities],
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rules
        ]
        acts = db.execute(
            select(Activity)
            .where(Activity.action.like("rule%"))
            .order_by(desc(Activity.created_at))
            .limit(50)
        ).scalars().all()
        activity_out = [
            {
                "at": a.created_at.isoformat() if a.created_at else None,
                "action": a.action,
                "target_id": a.target_id,
                "payload": a.payload,
            }
            for a in acts
        ]
    return {
        "matches": len(rules_out),
        "rules": rules_out,
        "recent_rule_activity": activity_out,
    }


@router.get("/recover-archived-rules")
def recover_archived_rules(_: User = Depends(require_admin)) -> dict:
    """Admin-only, browser-openable recovery for rules stranded in the old
    'archived' status (the archive feature was removed; archived rows are
    invisible in the UI). Every archived rule goes back to the entity's
    Compliance tab as a discovered draft (status=staging,
    sent_to_review=false). Idempotent — a second run finds nothing. Open it
    in the browser while logged in as an admin:
    `/api/system/recover-archived-rules`.
    """
    from sqlalchemy import select

    from compliance_agent.db import Rule, RuleStatus, session_scope

    with session_scope() as db:
        rows = db.execute(
            select(Rule).where(Rule.status == RuleStatus.archived)
        ).scalars().all()
        names = []
        for r in rows:
            r.status = RuleStatus.staging
            r.sent_to_review = False
            names.append(
                f"{r.form_name or r.name} ({', '.join(e.name for e in r.entities) or 'no entity'})"
            )
        db.commit()
    return {
        "recovered": len(names),
        "rules": names,
        "note": "These are back on their entity's Compliance tab as discovered drafts.",
    }


@router.get("/db")
def db_info(_: User = Depends(require_admin)) -> dict:
    """Admin-only, browser-openable: WHICH database is this app actually using?

    Exists because `db/base.py` falls back to a local SQLite file when the
    configured Postgres is unreachable (Render's free Postgres expires after 90
    days). The service still boots, auto-creates an empty schema and seeds a
    bootstrap admin — so the app looks fine but every count reads 0 and it looks
    like the data was deleted. Nothing was deleted: the app is pointed at an
    empty database while the real one sits untouched.

    `on_fallback: true` is that exact situation, and the smoking gun to check
    first. Open `/api/system/db` in the browser while logged in as an admin.

    The connection string is redacted — host and database name only, never the
    password.
    """
    import os

    from sqlalchemy import func, inspect, select

    from compliance_agent.db.base import DATABASE_URL, engine

    def _redact(url: str) -> str:
        """Host + database only; strip driver, user and password entirely."""
        if "://" not in url:
            return url
        scheme, rest = url.split("://", 1)
        scheme = scheme.split("+", 1)[0]
        if "@" in rest:
            rest = rest.rsplit("@", 1)[1]
        return f"{scheme}://{rest}"

    configured = (os.environ.get("COMPLIANCE_DB_URL") or "").strip()
    is_sqlite = DATABASE_URL.startswith("sqlite")
    # Postgres was configured but we ended up on SQLite → the silent fallback ran.
    on_fallback = bool(configured) and is_sqlite

    counts: dict = {}
    try:
        present = set(inspect(engine).get_table_names())
        from compliance_agent.db import models as _m

        for label, model in (
            ("entities", _m.Entity),
            ("rules", _m.Rule),
            ("obligations", _m.Obligation),
            ("licenses", _m.License),
            ("users", _m.User),
            ("documents", _m.Document),
            ("file_blobs", _m.FileBlob),
            ("activities", _m.Activity),
        ):
            table = model.__table__
            if table.name not in present:
                counts[label] = None
                continue
            with engine.connect() as conn:
                counts[label] = int(
                    conn.execute(select(func.count()).select_from(table)).scalar_one()
                )
    except Exception as e:  # noqa: BLE001 — diagnostics must never 500
        counts["error"] = f"{type(e).__name__}: {e}"

    empty = counts.get("entities") == 0 and counts.get("rules") == 0

    if on_fallback:
        verdict = (
            "FALLBACK ACTIVE — Postgres is configured but UNREACHABLE, so the app "
            "is running on a local, ephemeral SQLite file. Your real data is still "
            "in that Postgres. Do NOT re-enter data here: this file is wiped on "
            "every redeploy. Fix the Postgres connection (or restore the database), "
            "then set COMPLIANCE_DB_STRICT=1 so this can never happen silently."
        )
    elif is_sqlite and not configured:
        verdict = (
            "SQLite by configuration — no COMPLIANCE_DB_URL is set. On a PaaS this "
            "file is ephemeral and lost on redeploy; set COMPLIANCE_DB_URL to a "
            "managed Postgres."
        )
    elif empty:
        verdict = (
            "Connected to the configured Postgres, but it is EMPTY. This is a "
            "different/new database, not the one holding your data — check that "
            "COMPLIANCE_DB_URL points at the right instance."
        )
    else:
        verdict = "OK — connected to the configured database and it holds data."

    return {
        "dialect": "sqlite" if is_sqlite else engine.dialect.name,
        "in_use": _redact(DATABASE_URL),
        "configured_db_url_set": bool(configured),
        "configured_target": _redact(configured) if configured else None,
        "on_fallback": on_fallback,
        "strict_mode": os.environ.get("COMPLIANCE_DB_STRICT") == "1",
        "looks_empty": empty,
        "row_counts": counts,
        "verdict": verdict,
    }


@router.get("/repair-schema")
def repair_schema(_: User = Depends(require_admin)) -> dict:
    """Admin-only, browser-openable schema repair (no shell, no DB client).

    Adds any column the model expects that the live DB is missing — chiefly
    `entities.status`, whose absence breaks every entity query — and reports the
    result, INCLUDING the exact DB error if an ALTER is rejected. Idempotent and
    safe to re-run. Open it in the browser while logged in as an admin:
    `/api/system/repair-schema`.
    """
    from sqlalchemy import text

    from compliance_agent.db.base import _add_missing_columns, engine

    results: list[str] = []

    # 1) Directly ensure the column that's been breaking entity queries. Each
    #    statement runs in its own transaction so one failure doesn't block the
    #    rest, and any DB error is returned verbatim for diagnosis.
    for stmt in (
        "ALTER TABLE entities ADD COLUMN IF NOT EXISTS status "
        "VARCHAR(16) DEFAULT 'not_started'",
        "UPDATE entities SET status = 'not_started' WHERE status IS NULL",
    ):
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
            results.append(f"OK: {stmt.split(' ADD COLUMN')[0].split(' SET')[0]}")
        except Exception as e:  # noqa: BLE001
            results.append(f"FAILED: {type(e).__name__}: {e}")

    # 2) Re-run the full idempotent column migration, best-effort.
    try:
        _add_missing_columns()
        results.append("OK: ran _add_missing_columns()")
    except Exception as e:  # noqa: BLE001
        results.append(f"FAILED: _add_missing_columns -> {type(e).__name__}: {e}")

    return {"results": results}

