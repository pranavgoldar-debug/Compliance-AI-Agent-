"""User management endpoints — list (any user) + admin CRUD (admin only).

Admin invites: admin sets the initial password manually; we show it once in
the response, never again. Real magic-link email invites land in Phase 6 when
SMTP is wired up.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_agent.api._helpers import log_activity
from compliance_agent.api.schemas import (
    UserBrief,
    UserCreate,
    UserOut,
    UserUpdate,
)
from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.auth.passwords import hash_password
from compliance_agent.db import Role, User, get_session


router = APIRouter(prefix="/api/users", tags=["users"])


# ---------------------------------------------------------------------------
# Lightweight list — used by the assignee picker. Every authed user reads.
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Admin CRUD
# ---------------------------------------------------------------------------
@router.get("/admin", response_model=list[UserOut])
def list_users_admin(
    db: Session = Depends(get_session),
    _: User = Depends(require_admin),
) -> list[UserOut]:
    """Full user list incl. inactive users. Admin only."""
    stmt = select(User).order_by(User.is_active.desc(), User.full_name, User.email)
    return [UserOut.model_validate(u) for u in db.execute(stmt).scalars().all()]


@router.post("/admin", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> UserOut:
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required.")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="A user with that email already exists.")
    from compliance_agent.db import Department as _Department

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=(payload.full_name or "").strip() or email.split("@")[0],
        role=payload.role,
        is_active=True,
        department=(_Department(payload.department) if payload.department else None),
    )
    db.add(user)
    db.flush()
    log_activity(
        db,
        actor_id=actor.id,
        action="user.created",
        target_type="user",
        target_id=user.id,
        payload={"email": user.email, "role": user.role.value},
    )
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/admin/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    data = payload.model_dump(exclude_unset=True)

    # Don't let an admin demote / deactivate themselves — risks locking out the workspace.
    if user.id == actor.id:
        if data.get("role") and data["role"] != Role.admin:
            raise HTTPException(status_code=400, detail="You can't demote your own account.")
        if data.get("is_active") is False:
            raise HTTPException(status_code=400, detail="You can't deactivate your own account.")

    if "password" in data and data["password"] is not None:
        if len(data["password"]) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
        user.password_hash = hash_password(data.pop("password"))

    if "department" in data:
        from compliance_agent.db import Department as _Department

        raw = data.pop("department")
        user.department = _Department(raw) if raw else None

    for field, value in data.items():
        if value is not None:
            setattr(user, field, value)

    log_activity(
        db,
        actor_id=actor.id,
        action="user.updated",
        target_type="user",
        target_id=user.id,
        payload={"fields": list(data.keys())},
    )
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.delete("/admin/{user_id}", status_code=204)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> None:
    """Soft delete — sets is_active=False so existing references stay intact."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.id == actor.id:
        raise HTTPException(status_code=400, detail="You can't deactivate your own account.")
    user.is_active = False
    log_activity(
        db,
        actor_id=actor.id,
        action="user.deactivated",
        target_type="user",
        target_id=user.id,
    )
    db.commit()
