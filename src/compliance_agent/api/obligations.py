"""Obligation list / detail / update endpoints + comments + calendar."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from compliance_agent.api._helpers import (
    ALERT_WINDOW_DAYS,
    is_awaiting_payment,
    log_activity,
    serialize_calendar_obligation,
    serialize_obligation,
    serialize_user,
    today,
)
from compliance_agent.api.notifications import (
    emit_assignment,
    emit_mentions,
    emit_payment_request,
    emit_status_change,
    extract_mentions,
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
    Department,
    Notification,
    NotificationKind,
    Obligation,
    ObligationStatus,
    Role,
    User,
    get_session,
)
from compliance_agent import slack_service


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
    obligation = db.execute(
        _base_query().where(Obligation.id == obligation_id)
    ).scalars().unique().one_or_none()
    if obligation is None:
        raise HTTPException(status_code=404, detail="Obligation not found.")

    data = payload.model_dump(exclude_unset=True)

    # Reassigning work is an admin-only action. Employees can self-update
    # status / filing fields on items they own, but they can't push work to
    # other people.
    if "assignee_id" in data and user.role != Role.admin:
        new_assignee = data.get("assignee_id")
        if new_assignee != obligation.assignee_id:
            raise HTTPException(
                status_code=403,
                detail="Only admins can change assignees.",
            )

    completed_now = (
        data.get("status") == ObligationStatus.completed
        and obligation.status != ObligationStatus.completed
    )
    uncompleted_now = (
        data.get("status") is not None
        and data["status"] != ObligationStatus.completed
        and obligation.status == ObligationStatus.completed
    )

    # Capture old values so we can compare-and-emit notifications.
    prev_assignee_id = obligation.assignee_id
    prev_status = obligation.status

    for field, value in data.items():
        setattr(obligation, field, value)

    if completed_now:
        obligation.completed_at = datetime.now(tz=timezone.utc)
        obligation.completed_by_id = user.id
    if uncompleted_now:
        obligation.completed_at = None
        obligation.completed_by_id = None

    # Notifications: assignee changed → ping the new owner.
    if "assignee_id" in data and obligation.assignee_id and obligation.assignee_id != prev_assignee_id:
        new_assignee = db.get(User, obligation.assignee_id)
        if new_assignee:
            emit_assignment(db, assignee=new_assignee, obligation=obligation, actor=user)

    # Notifications: status moved to completed / pending_review → ping assignee.
    if "status" in data and obligation.status != prev_status:
        assignee = obligation.assignee or (
            db.get(User, obligation.assignee_id) if obligation.assignee_id else None
        )
        emit_status_change(
            db,
            assignee=assignee,
            obligation=obligation,
            new_status=obligation.status,
            actor=user,
        )
        # Filing was just approved AND the rule has a payment leg → fire an
        # explicit "payment requested" notification so finance doesn't have
        # to come check the Awaiting payment chip.
        if completed_now and is_awaiting_payment(obligation):
            emit_payment_request(db, obligation=obligation, actor=user)

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
    obligation = db.execute(
        _base_query().where(Obligation.id == obligation_id)
    ).scalars().unique().one_or_none()
    if obligation is None:
        raise HTTPException(status_code=404, detail="Obligation not found.")
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Comment body is required.")
    comment = Comment(obligation_id=obligation_id, author_id=user.id, body=body)
    db.add(comment)
    db.flush()  # need comment.id for the mention notification's comment_id

    mentions = extract_mentions(db, body)
    if mentions:
        emit_mentions(
            db,
            mentions=mentions,
            actor=user,
            obligation=obligation,
            comment_id=comment.id,
            body=body,
        )

    log_activity(
        db,
        actor_id=user.id,
        action="comment.added",
        target_type="obligation",
        target_id=obligation_id,
        payload={"mentions": [u.email for u in mentions]} if mentions else None,
    )
    db.commit()
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
# Bulk operations — assign / change status across many obligations at once.
# ---------------------------------------------------------------------------
from pydantic import BaseModel as _BaseModel


class HandoffPayload(_BaseModel):
    finance_user_id: int
    notes: Optional[str] = None


class HandoffResponse(_BaseModel):
    obligation_id: int
    new_assignee_id: int
    new_status: ObligationStatus


@router.post(
    "/{obligation_id}/handoff-to-finance",
    response_model=HandoffResponse,
)
def handoff_to_finance(
    obligation_id: int,
    payload: HandoffPayload,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> HandoffResponse:
    """Admin marks the filing leg approved and reassigns the obligation to
    a finance team member, who'll now log the payment + UTR. Status flips
    from pending_review back to in_progress (work continues, just by a
    different team).
    """
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Only admins can hand off filings.")

    obligation = db.execute(
        _base_query().where(Obligation.id == obligation_id)
    ).scalars().unique().one_or_none()
    if obligation is None:
        raise HTTPException(status_code=404, detail="Obligation not found.")

    if obligation.status != ObligationStatus.pending_review:
        raise HTTPException(
            status_code=400,
            detail=(
                "Hand-off only applies when the filing is awaiting your review. "
                "Current status: " + obligation.status.value + "."
            ),
        )

    finance_user = db.get(User, payload.finance_user_id)
    if finance_user is None or not finance_user.is_active:
        raise HTTPException(status_code=400, detail="Finance team member not found.")

    prev_assignee_id = obligation.assignee_id
    obligation.assignee_id = finance_user.id
    obligation.status = ObligationStatus.in_progress
    obligation.department = Department.finance
    if payload.notes:
        # Append to existing notes rather than overwriting compliance's notes.
        prefix = (obligation.notes + "\n\n") if obligation.notes else ""
        obligation.notes = (
            prefix
            + f"[Admin → Finance handoff by {user.full_name or user.email}]: "
            + payload.notes
        )

    # Notification + Slack ping so finance knows they own this now.
    rule = obligation.rule
    entity = obligation.entity
    form = rule.form_name if rule else "Compliance item"
    entity_name = entity.name if entity else "—"
    db.add(
        Notification(
            user_id=finance_user.id,
            kind=NotificationKind.payment_request,
            title=f"Filing approved — log payment for {form}",
            body=(
                f"{entity_name} · {user.full_name or user.email} verified the "
                f"filing. Enter the payment amount + UTR, then submit for "
                f"final review."
            ),
            link_url=f"/obligations/{obligation.id}",
            obligation_id=obligation.id,
            actor_id=user.id,
        )
    )
    if slack_service.is_configured(db):
        slack_service.post(
            f":money_with_wings: *Payment requested* — *{form}* ({entity_name}). "
            f"Filing approved by {user.full_name or user.email}. "
            f"Assigned to {finance_user.full_name or finance_user.email} to pay."
        )

    log_activity(
        db,
        actor_id=user.id,
        action="obligation.handoff_to_finance",
        target_type="obligation",
        target_id=obligation.id,
        payload={
            "prev_assignee_id": prev_assignee_id,
            "finance_user_id": finance_user.id,
        },
    )
    db.commit()
    return HandoffResponse(
        obligation_id=obligation.id,
        new_assignee_id=finance_user.id,
        new_status=obligation.status,
    )


class BulkUpdateRequest(_BaseModel):
    obligation_ids: list[int]
    status: Optional[ObligationStatus] = None
    assignee_id: Optional[int] = None
    # If True, send assignee_id=null to clear the assignee.
    clear_assignee: bool = False


class BulkUpdateResult(_BaseModel):
    updated: int
    skipped: list[int] = []


@router.post("/bulk-update", response_model=BulkUpdateResult)
def bulk_update(
    payload: BulkUpdateRequest,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkUpdateResult:
    if not payload.obligation_ids:
        return BulkUpdateResult(updated=0)
    if payload.status is None and payload.assignee_id is None and not payload.clear_assignee:
        raise HTTPException(
            status_code=400, detail="Provide at least one of status, assignee_id, clear_assignee."
        )
    # Admin-only: bulk reassignment moves work between people.
    if (payload.assignee_id is not None or payload.clear_assignee) and user.role != Role.admin:
        raise HTTPException(
            status_code=403,
            detail="Only admins can change assignees.",
        )

    obligations = db.execute(
        _base_query().where(Obligation.id.in_(payload.obligation_ids))
    ).scalars().unique().all()

    by_id = {o.id: o for o in obligations}
    missing = [i for i in payload.obligation_ids if i not in by_id]

    new_assignee: Optional[User] = None
    if payload.assignee_id is not None and not payload.clear_assignee:
        new_assignee = db.get(User, payload.assignee_id)
        if new_assignee is None:
            raise HTTPException(status_code=400, detail="Assignee not found.")

    updated = 0
    for o in obligations:
        changed_fields: list[str] = []
        prev_assignee_id = o.assignee_id
        prev_status = o.status

        if payload.status is not None and payload.status != o.status:
            o.status = payload.status
            changed_fields.append("status")
            if payload.status == ObligationStatus.completed and o.completed_at is None:
                o.completed_at = datetime.now(tz=timezone.utc)
                o.completed_by_id = user.id
            elif payload.status != ObligationStatus.completed and o.completed_at is not None:
                o.completed_at = None
                o.completed_by_id = None

        if payload.clear_assignee:
            if o.assignee_id is not None:
                o.assignee_id = None
                changed_fields.append("assignee_id")
        elif new_assignee is not None and o.assignee_id != new_assignee.id:
            o.assignee_id = new_assignee.id
            changed_fields.append("assignee_id")

        if not changed_fields:
            continue
        updated += 1

        if "assignee_id" in changed_fields and new_assignee is not None and prev_assignee_id != new_assignee.id:
            emit_assignment(db, assignee=new_assignee, obligation=o, actor=user)
        if "status" in changed_fields and o.status != prev_status:
            assignee = o.assignee or (db.get(User, o.assignee_id) if o.assignee_id else None)
            emit_status_change(
                db, assignee=assignee, obligation=o, new_status=o.status, actor=user
            )
            if (
                o.status == ObligationStatus.completed
                and prev_status != ObligationStatus.completed
                and is_awaiting_payment(o)
            ):
                emit_payment_request(db, obligation=o, actor=user)

        log_activity(
            db,
            actor_id=user.id,
            action="obligation.updated",
            target_type="obligation",
            target_id=o.id,
            payload={"changed_fields": changed_fields, "bulk": True},
        )

    db.commit()
    return BulkUpdateResult(updated=updated, skipped=missing)


# ---------------------------------------------------------------------------
# Calendar — compact records for a month grid
# ---------------------------------------------------------------------------
calendar_router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@calendar_router.get("", response_model=list[CalendarObligation])
def calendar_range(
    start: date = Query(..., description="Inclusive start of date range."),
    end: date = Query(..., description="Inclusive end of date range."),
    entity_id: Optional[int] = Query(None),
    entity_ids: Optional[list[int]] = Query(None),
    jurisdiction_code: Optional[str] = Query(None),
    jurisdiction_codes: Optional[list[str]] = Query(None),
    category: Optional[str] = Query(None),
    categories: Optional[list[str]] = Query(None),
    assignee_id: Optional[int] = Query(None),
    assignee_ids: Optional[list[int]] = Query(None),
    status: Optional[ObligationStatus] = Query(None),
    statuses: Optional[list[ObligationStatus]] = Query(None),
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[CalendarObligation]:
    if (end - start).days > 400:
        raise HTTPException(status_code=400, detail="Date range too wide (max 400 days).")
    stmt = (
        select(Obligation)
        .where(Obligation.due_date >= start, Obligation.due_date <= end)
        .options(
            joinedload(Obligation.rule),
            joinedload(Obligation.entity),
            joinedload(Obligation.assignee),
        )
        .order_by(Obligation.due_date.asc())
    )
    if entity_id is not None:
        stmt = stmt.where(Obligation.entity_id == entity_id)
    if entity_ids:
        stmt = stmt.where(Obligation.entity_id.in_(entity_ids))
    if assignee_id is not None:
        stmt = stmt.where(Obligation.assignee_id == assignee_id)
    if assignee_ids:
        stmt = stmt.where(Obligation.assignee_id.in_(assignee_ids))
    if status is not None:
        stmt = stmt.where(Obligation.status == status)
    if statuses:
        stmt = stmt.where(Obligation.status.in_(statuses))
    items = db.execute(stmt).scalars().unique().all()
    if jurisdiction_code:
        items = [o for o in items if o.rule.jurisdiction_code == jurisdiction_code]
    if jurisdiction_codes:
        codes = set(jurisdiction_codes)
        items = [o for o in items if o.rule.jurisdiction_code in codes]
    if category:
        items = [o for o in items if o.rule.category == category]
    if categories:
        cats = set(categories)
        items = [o for o in items if o.rule.category in cats]
    return [serialize_calendar_obligation(o) for o in items]
