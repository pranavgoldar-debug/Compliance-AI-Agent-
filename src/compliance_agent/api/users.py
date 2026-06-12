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
from compliance_agent.db import Department, Role, User, get_session


router = APIRouter(prefix="/api/users", tags=["users"])


def _parse_department(raw: object) -> Department | None:
    """Accepts a department string from the API payload. Empty string clears
    the field; None leaves it unset (caller decides). Invalid values raise."""
    if raw is None or raw == "":
        return None
    try:
        return Department(raw)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown department '{raw}'. Pick one of: "
            f"{', '.join(d.value for d in Department)}.",
        ) from e


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
    dept = _parse_department(payload.department)
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=(payload.full_name or "").strip() or email.split("@")[0],
        role=payload.role,
        department=dept,
        is_active=True,
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

    # Department is special: empty string means "clear it" (set to NULL),
    # otherwise validate against the enum. Pop it out of the generic loop.
    if "department" in data:
        user.department = _parse_department(data.pop("department"))

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


@router.delete("/admin/{user_id}")
def deactivate_user(
    user_id: int,
    reassign_to: int | None = None,
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> dict:
    """Deactivate a user (audit-safe soft delete — is_active=False, history
    kept) AND clear their workload so it doesn't strand: their OPEN filings are
    handed to ``reassign_to`` if given, otherwise unassigned (so they surface in
    Filings → Unassigned). Pending Google Calendar events follow; reminders stop
    (the reminder job skips inactive assignees)."""
    from compliance_agent.db import Obligation, ObligationStatus
    from compliance_agent.api.notifications import emit_assignment
    from compliance_agent import calendar_service

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.id == actor.id:
        raise HTTPException(status_code=400, detail="You can't deactivate your own account.")

    new_owner: User | None = None
    if reassign_to is not None:
        new_owner = db.get(User, reassign_to)
        if new_owner is None or not new_owner.is_active:
            raise HTTPException(status_code=400, detail="Reassignee must be an active user.")
        if new_owner.id == user.id:
            raise HTTPException(status_code=400, detail="Can't reassign to the user being deactivated.")

    open_obs = db.execute(
        select(Obligation).where(
            Obligation.assignee_id == user.id,
            Obligation.status.not_in(
                [ObligationStatus.completed, ObligationStatus.not_applicable]
            ),
        )
    ).scalars().all()
    for ob in open_obs:
        ob.assignee_id = new_owner.id if new_owner else None

    user.is_active = False
    log_activity(
        db,
        actor_id=actor.id,
        action="user.deactivated",
        target_type="user",
        target_id=user.id,
        payload={
            "open_filings": len(open_obs),
            "reassigned_to": new_owner.id if new_owner else None,
        },
    )
    db.commit()

    # Post-commit fan-out: notify the new owner of each handed-over filing, and
    # keep the shared Google Calendar in step (reassign → update, unassign → remove).
    if new_owner:
        for ob in open_obs:
            try:
                emit_assignment(db, assignee=new_owner, obligation=ob, actor=actor)
            except Exception:  # noqa: BLE001
                pass
    if calendar_service.is_configured():
        for ob in open_obs:
            calendar_service.sync_obligation(ob.id)

    return {
        "deactivated": True,
        "open_filings": len(open_obs),
        "reassigned_to": new_owner.id if new_owner else None,
    }

