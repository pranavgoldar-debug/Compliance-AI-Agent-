"""Obligation list / detail / update endpoints + comments + calendar."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from compliance_agent.api._helpers import (
    ALERT_WINDOW_DAYS,
    log_activity,
    serialize_calendar_obligation,
    serialize_obligation,
    serialize_user,
    today,
)
from compliance_agent.api.schemas import (
    CalendarObligation,
    CommentCreate,
    CommentOut,
    ObligationOut,
    ObligationUpdate,
)
from compliance_agent.auth import get_current_user
from compliance_agent.db import (
    Comment,
    Obligation,
    ObligationStatus,
    User,
    get_session,
)


router = APIRouter(prefix="/api/obligations", tags=["obligations"])


def _base_query():
    return select(Obligation).options(
        joinedload(Obligation.rule),
        joinedload(Obligation.entity),
        joinedload(Obligation.assignee),
    )


@router.get("", response_model=list[ObligationOut])
def list_obligations(
    entity_id: Optional[int] = Query(None),
    assignee_id: Optional[int] = Query(None, description="Filter by assigned user; pass 'me' via /tasks endpoint instead"),
    status: Optional[ObligationStatus] = Query(None),
    jurisdiction_code: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    due_from: Optional[date] = Query(None),
    due_to: Optional[date] = Query(None),
    limit: int = Query(500, le=2000),
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[ObligationOut]:
    stmt = _base_query()
    if entity_id is not None:
        stmt = stmt.where(Obligation.entity_id == entity_id)
    if assignee_id is not None:
        stmt = stmt.where(Obligation.assignee_id == assignee_id)
    if status is not None:
        stmt = stmt.where(Obligation.status == status)
    if due_from is not None:
        stmt = stmt.where(Obligation.due_date >= due_from)
    if due_to is not None:
        stmt = stmt.where(Obligation.due_date <= due_to)
    stmt = stmt.order_by(Obligation.due_date.asc()).limit(limit)

    items = db.execute(stmt).scalars().unique().all()

    # Jurisdiction / category filters require the rule join — apply in Python
    # because they live on Rule and we already loaded the rule.
    if jurisdiction_code:
        items = [o for o in items if o.rule.jurisdiction_code == jurisdiction_code]
    if category:
        items = [o for o in items if o.rule.category == category]

    return [serialize_obligation(o) for o in items]


@router.get("/{obligation_id}", response_model=ObligationOut)
def get_obligation(
    obligation_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> ObligationOut:
    o = db.execute(_base_query().where(Obligation.id == obligation_id)).scalars().unique().one_or_none()
    if o is None:
        raise HTTPException(status_code=404, detail="Obligation not found.")
    return serialize_obligation(o)


@router.patch("/{obligation_id}", response_model=ObligationOut)
def update_obligation(
    obligation_id: int,
    payload: ObligationUpdate,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ObligationOut:
    obligation = db.get(Obligation, obligation_id)
    if obligation is None:
        raise HTTPException(status_code=404, detail="Obligation not found.")

    data = payload.model_dump(exclude_unset=True)
    completed_now = (
        data.get("status") == ObligationStatus.completed
        and obligation.status != ObligationStatus.completed
    )
    uncompleted_now = (
        data.get("status") is not None
        and data["status"] != ObligationStatus.completed
        and obligation.status == ObligationStatus.completed
    )

    for field, value in data.items():
        setattr(obligation, field, value)

    if completed_now:
        obligation.completed_at = datetime.now(tz=timezone.utc)
        obligation.completed_by_id = user.id
    if uncompleted_now:
        obligation.completed_at = None
        obligation.completed_by_id = None

    log_activity(
        db,
        actor_id=user.id,
        action="obligation.updated",
        target_type="obligation",
        target_id=obligation.id,
        payload={"changed_fields": list(data.keys())},
    )
    db.commit()
    obligation = db.execute(
        _base_query().where(Obligation.id == obligation.id)
    ).scalars().unique().one()
    return serialize_obligation(obligation)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------
@router.get("/{obligation_id}/comments", response_model=list[CommentOut])
def list_comments(
    obligation_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[CommentOut]:
    obligation = db.get(Obligation, obligation_id)
    if obligation is None:
        raise HTTPException(status_code=404, detail="Obligation not found.")
    items = db.execute(
        select(Comment)
        .where(Comment.obligation_id == obligation_id)
        .options(joinedload(Comment.author))
        .order_by(Comment.created_at.asc())
    ).scalars().unique().all()
    return [
        CommentOut(
            id=c.id,
            obligation_id=c.obligation_id,
            author=serialize_user(c.author),
            body=c.body,
            created_at=c.created_at,
        )
        for c in items
    ]


@router.post("/{obligation_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(
    obligation_id: int,
    payload: CommentCreate,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CommentOut:
    obligation = db.get(Obligation, obligation_id)
    if obligation is None:
        raise HTTPException(status_code=404, detail="Obligation not found.")
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Comment body is required.")
    comment = Comment(obligation_id=obligation_id, author_id=user.id, body=body)
    db.add(comment)
    log_activity(
        db,
        actor_id=user.id,
        action="comment.added",
        target_type="obligation",
        target_id=obligation_id,
    )
    db.commit()
    db.refresh(comment)
    comment = db.execute(
        select(Comment).where(Comment.id == comment.id).options(joinedload(Comment.author))
    ).scalars().unique().one()
    return CommentOut(
        id=comment.id,
        obligation_id=comment.obligation_id,
        author=serialize_user(comment.author),
        body=comment.body,
        created_at=comment.created_at,
    )


# ---------------------------------------------------------------------------
# Calendar — compact records for a month grid
# ---------------------------------------------------------------------------
calendar_router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@calendar_router.get("", response_model=list[CalendarObligation])
def calendar_range(
    start: date = Query(..., description="Inclusive start of date range."),
    end: date = Query(..., description="Inclusive end of date range."),
    entity_id: Optional[int] = Query(None),
    jurisdiction_code: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    assignee_id: Optional[int] = Query(None),
    status: Optional[ObligationStatus] = Query(None),
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[CalendarObligation]:
    if (end - start).days > 400:
        raise HTTPException(status_code=400, detail="Date range too wide (max 400 days).")
    stmt = (
        select(Obligation)
        .where(Obligation.due_date >= start, Obligation.due_date <= end)
        .options(joinedload(Obligation.rule), joinedload(Obligation.entity))
        .order_by(Obligation.due_date.asc())
    )
    if entity_id is not None:
        stmt = stmt.where(Obligation.entity_id == entity_id)
    if assignee_id is not None:
        stmt = stmt.where(Obligation.assignee_id == assignee_id)
    if status is not None:
        stmt = stmt.where(Obligation.status == status)
    items = db.execute(stmt).scalars().unique().all()
    if jurisdiction_code:
        items = [o for o in items if o.rule.jurisdiction_code == jurisdiction_code]
    if category:
        items = [o for o in items if o.rule.category == category]
    return [serialize_calendar_obligation(o) for o in items]
