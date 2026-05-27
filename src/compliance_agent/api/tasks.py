"""Tasks endpoint — obligations filtered to a user.

Powers the Tasks page (Assigned to me / Watching / Completed / All).
'Watching' is a placeholder for now — when comments / mentions are implemented
this can list obligations the user has interacted with.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from compliance_agent.api._helpers import serialize_obligation
from compliance_agent.api.schemas import ObligationOut
from compliance_agent.auth import get_current_user
from compliance_agent.db import Comment, Obligation, ObligationStatus, User, get_session


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[ObligationOut])
def list_my_tasks(
    scope: str = Query("assigned", pattern=r"^(assigned|watching|completed|all)$"),
    department: Optional[str] = Query(
        None,
        pattern=r"^(compliance|finance|legal|risk|operations)$",
        description="If set, only return obligations owned by this department.",
    ),
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ObligationOut]:
    base = select(Obligation).options(
        joinedload(Obligation.rule),
        joinedload(Obligation.entity),
        joinedload(Obligation.assignee),
    )
    if scope == "assigned":
        stmt = base.where(Obligation.assignee_id == user.id).where(
            Obligation.status.notin_([ObligationStatus.completed, ObligationStatus.not_applicable])
        )
    elif scope == "completed":
        stmt = base.where(Obligation.status == ObligationStatus.completed).where(
            or_(Obligation.assignee_id == user.id, Obligation.completed_by_id == user.id)
        )
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
    return [serialize_obligation(o) for o in items]
