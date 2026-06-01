"""Activity / audit-log endpoint.

The Activity table is already populated by every mutating endpoint via
`log_activity`. This module exposes a chronological read API for the UI:
the full feed (admin) plus scoped views by entity / obligation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete as _sa_delete, func, select
from sqlalchemy.orm import Session, joinedload

from compliance_agent.api._helpers import serialize_user
from compliance_agent.api.schemas import ActivityOut
from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.db import (
    Activity,
    Document,
    Entity,
    Obligation,
    Rule,
    User,
    get_session,
)


router = APIRouter(prefix="/api/activities", tags=["activities"])


# ---------------------------------------------------------------------------
# Target label resolution — turn (target_type, target_id) into a human label
# so the feed can render "<actor> updated <thing>" without N+1 queries on the
# client. Resolved in a single batch per response.
# ---------------------------------------------------------------------------
def _resolve_labels(
    db: Session, rows: list[Activity]
) -> dict[tuple[str, int], str]:
    """Returns a (target_type, target_id) → label dict."""
    needed: dict[str, set[int]] = {}
    for a in rows:
        if not a.target_type or not a.target_id:
            continue
        needed.setdefault(a.target_type, set()).add(a.target_id)

    labels: dict[tuple[str, int], str] = {}

    if ids := needed.get("obligation"):
        for ob in db.execute(
            select(Obligation)
            .where(Obligation.id.in_(ids))
            .options(joinedload(Obligation.rule), joinedload(Obligation.entity))
        ).scalars().unique().all():
            labels[("obligation", ob.id)] = (
                f"{ob.entity.name} — {ob.rule.form_name}"
                if ob.entity and ob.rule
                else f"Obligation #{ob.id}"
            )

    if ids := needed.get("entity"):
        for ent in db.execute(
            select(Entity).where(Entity.id.in_(ids))
        ).scalars().all():
            labels[("entity", ent.id)] = ent.name

    if ids := needed.get("rule"):
        for r in db.execute(select(Rule).where(Rule.id.in_(ids))).scalars().all():
            labels[("rule", r.id)] = r.form_name

    if ids := needed.get("document"):
        for d in db.execute(
            select(Document).where(Document.id.in_(ids))
        ).scalars().all():
            labels[("document", d.id)] = d.filename

    if ids := needed.get("user"):
        for u in db.execute(select(User).where(User.id.in_(ids))).scalars().all():
            labels[("user", u.id)] = u.full_name or u.email

    return labels


def _serialize(a: Activity, labels: dict[tuple[str, int], str]) -> ActivityOut:
    label = None
    if a.target_type and a.target_id:
        label = labels.get((a.target_type, a.target_id))
    return ActivityOut(
        id=a.id,
        actor=serialize_user(a.actor),
        action=a.action,
        target_type=a.target_type,
        target_id=a.target_id,
        target_label=label,
        payload=a.payload,
        created_at=a.created_at,
    )


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------
@router.get("", response_model=list[ActivityOut])
def list_activities(
    entity_id: Optional[int] = Query(None),
    obligation_id: Optional[int] = Query(None),
    actor_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None, description="Exact action name, e.g. 'obligation.updated'"),
    action_prefix: Optional[str] = Query(None, description="Match any action starting with this"),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[ActivityOut]:
    stmt = (
        select(Activity)
        .options(joinedload(Activity.actor))
        .order_by(Activity.created_at.desc(), Activity.id.desc())
    )
    if actor_id is not None:
        stmt = stmt.where(Activity.actor_id == actor_id)
    if action is not None:
        stmt = stmt.where(Activity.action == action)
    if action_prefix is not None:
        stmt = stmt.where(Activity.action.like(f"{action_prefix}%"))
    if since is not None:
        stmt = stmt.where(Activity.created_at >= since)
    if until is not None:
        stmt = stmt.where(Activity.created_at <= until)

    # Scoping by entity / obligation is a little subtle:
    # - Direct activities on the target are easy.
    # - For entity scope we ALSO want activities on this entity's obligations.
    if obligation_id is not None:
        stmt = stmt.where(
            (Activity.target_type == "obligation") & (Activity.target_id == obligation_id),
        )
    elif entity_id is not None:
        ob_ids = [
            row[0]
            for row in db.execute(
                select(Obligation.id).where(Obligation.entity_id == entity_id)
            ).all()
        ]
        doc_ids = [
            row[0]
            for row in db.execute(
                select(Document.id).where(Document.entity_id == entity_id)
            ).all()
        ]
        conditions = [
            (Activity.target_type == "entity") & (Activity.target_id == entity_id),
        ]
        if ob_ids:
            conditions.append(
                (Activity.target_type == "obligation") & (Activity.target_id.in_(ob_ids))
            )
        if doc_ids:
            conditions.append(
                (Activity.target_type == "document") & (Activity.target_id.in_(doc_ids))
            )
        clause = conditions[0]
        for c in conditions[1:]:
            clause = clause | c
        stmt = stmt.where(clause)

    stmt = stmt.offset(offset).limit(limit)
    rows = db.execute(stmt).scalars().unique().all()
    labels = _resolve_labels(db, list(rows))
    return [_serialize(a, labels) for a in rows]


@router.get("/export", tags=["activities"])
def export_activities_csv(
    db: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    """Admin-only CSV export of the full audit log."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    rows = db.execute(
        select(Activity)
        .options(joinedload(Activity.actor))
        .order_by(Activity.created_at.desc())
        .limit(10_000)
    ).scalars().unique().all()
    labels = _resolve_labels(db, list(rows))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["timestamp_utc", "actor", "action", "target_type", "target_id", "target", "payload"])
    for a in rows:
        writer.writerow(
            [
                a.created_at.isoformat(),
                (a.actor.email if a.actor else ""),
                a.action,
                a.target_type or "",
                a.target_id or "",
                labels.get((a.target_type, a.target_id), "") if a.target_type and a.target_id else "",
                str(a.payload or ""),
            ]
        )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="aspora-audit-log.csv"'},
    )


class ClearResult(__import__("pydantic").BaseModel):
    deleted: int


@router.delete("", response_model=ClearResult)
def clear_activities(
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> ClearResult:
    """Admin-only: wipe the activity / audit log. Irreversible."""
    n = db.execute(select(func.count(Activity.id))).scalar_one()
    db.execute(_sa_delete(Activity))
    db.commit()
    return ClearResult(deleted=int(n or 0))
