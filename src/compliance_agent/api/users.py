"""User listing endpoint — needed for the assignee picker.

Returns active users only. All authenticated users can read; only admins
can write (write endpoints land in Phase 5 with full user management).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_agent.api.schemas import UserBrief
from compliance_agent.auth import get_current_user
from compliance_agent.db import User, get_session


router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserBrief])
def list_users(
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[UserBrief]:
    stmt = (
        select(User)
        .where(User.is_active.is_(True))
        .order_by(User.full_name, User.email)
    )
    return [UserBrief.model_validate(u) for u in db.execute(stmt).scalars().all()]
