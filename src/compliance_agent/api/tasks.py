"""Tasks endpoint — obligations filtered to a user.

Powers the Tasks page (Assigned to me / Watching / Completed / All).
'Watching' is a placeholder for now — when comments / mentions are implemented
this can list obligations the user has interacted with.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from compliance_agent.api._helpers import serialize_obligation
from compliance_agent.api.schemas import ObligationOut
from compliance_agent.auth import get_current_user
from compliance_agent.classification import keep_function
from compliance_agent.db import Comment, Entity, Obligation, ObligationStatus, User, get_session


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[ObligationOut])
def list_my_tasks(
    scope: str = Query("assigned", pattern=r"^(assigned|watching|completed|all)$"),
    department: Optional[str] = Query(
        None,
        pattern=r"^(compliance|finance|legal|risk|operations)$",
        description="If set, only return obligations owned by this department.",
    ),
    awaiting_payment: bool = Query(
        False,
        description=(
            "If true, only return items in the compliance→finance hand-off "
            "state: status=completed, rule has a payment_rule, no payment_reference yet."
        ),
    ),
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ObligationOut]:
    base = select(Obligation).where(
        # Skip obligations of archived entities — archiving hides its filings.
        Obligation.entity.has(Entity.archived_at.is_(None))
    ).options(
        joinedload(Obligation.rule),
        joinedload(Obligation.entity),
        joinedload(Obligation.assignee),
    )
    if scope == "assigned":
        stmt = base.where(Obligation.assignee_id == user.id).where(
            Obligation.status.notin_([ObligationStatus.completed, ObligationStatus.not_applicable])
        )
    elif scope == "completed":
        # Org-wide, like the "all" / "unassigned" tabs — the "Filed" tab COUNT is
        # derived org-wide (every completed obligation), so the list must match or
        # an admin sees "Filed (1)" with an empty list for a filing someone else
        # completed. "Assigned to me" stays the personal scope.
        stmt = base.where(Obligation.status == ObligationStatus.completed)
    elif scope == "watching":
        commented_ids = db.execute(
            select(Comment.obligation_id).where(Comment.author_id == user.id).distinct()
        ).scalars().all()
        if not commented_ids:
            return []
        stmt = base.where(Obligation.id.in_(commented_ids))
    else:  # all
        stmt = base

    if department:
        stmt = stmt.where(Obligation.department == department)

    stmt = stmt.order_by(Obligation.due_date.asc())
    items = db.execute(stmt).scalars().unique().all()
    # FINANCE_ONLY switch: hide non-Finance obligations from task lists.
    items = [
        o
        for o in items
        if o.rule is None
        or keep_function(o.rule.category, o.rule.area, o.rule.responsible_function)
    ]
    out = [serialize_obligation(o) for o in items]
    if awaiting_payment:
        out = [o for o in out if o.is_awaiting_payment]
    return out
