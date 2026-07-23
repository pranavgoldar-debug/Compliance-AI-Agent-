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

