"""Notifications API + helpers.

The inbox is a hybrid of persisted notifications (mention / assigned /
status_change) and live-derived notifications (overdue / alert_window).
The persisted ones live in `notifications`; the live ones are computed
from the user's open obligations on each request.

  GET    /api/notifications          → unified inbox
  POST   /api/notifications/read     → mark specific ids read
  POST   /api/notifications/read-all → mark every persisted notif read
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from compliance_agent.api._helpers import is_in_alert_window, is_overdue, serialize_user, today
from compliance_agent.api.schemas import UserBrief
from compliance_agent.auth import get_current_user
from compliance_agent.db import (
    EffortBand,
    Notification,
    NotificationKind,
    Obligation,
    ObligationStatus,
    User,
    get_session,
)


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------
class NotificationOut(BaseModel):
    id: Optional[int] = None  # null for derived notifications
    kind: NotificationKind
    title: str
    body: Optional[str] = None
    link_url: Optional[str] = None
    obligation_id: Optional[int] = None
    actor: Optional[UserBrief] = None
    read: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Listing — persisted + derived, sorted newest-first
# ---------------------------------------------------------------------------
@router.get("", response_model=list[NotificationOut])
def list_notifications(
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[NotificationOut]:
    persisted = db.execute(
        select(Notification)
        .where(Notification.user_id == user.id)
        .options(joinedload(Notification.actor))
        .order_by(Notification.created_at.desc())
        .limit(50)
    ).scalars().unique().all()

    out: list[NotificationOut] = []
    for n in persisted:
        out.append(
            NotificationOut(
                id=n.id,
                kind=n.kind,
                title=n.title,
                body=n.body,
                link_url=n.link_url,
                obligation_id=n.obligation_id,
                actor=serialize_user(n.actor),
                read=n.read_at is not None,
                created_at=n.created_at,
            )
        )

    # Derived — overdue + in-alert-window items assigned to this user.
    open_statuses = [
        ObligationStatus.not_started,
        ObligationStatus.in_progress,
        ObligationStatus.pending_review,
    ]
    my_open = db.execute(
        select(Obligation)
        .where(Obligation.assignee_id == user.id, Obligation.status.in_(open_statuses))
        .options(joinedload(Obligation.rule), joinedload(Obligation.entity))
    ).scalars().unique().all()

    for ob in my_open:
        band = ob.effort_band or EffortBand.w4
        if is_overdue(ob.due_date, ob.status):
            days_late = (today() - ob.due_date).days
            out.append(
                NotificationOut(
                    kind=NotificationKind.overdue,
                    title=f"{ob.rule.form_name} is overdue",
                    body=f"{ob.entity.name} · {days_late} day{'' if days_late == 1 else 's'} late",
                    link_url=f"/obligations/{ob.id}",
                    obligation_id=ob.id,
                    read=False,
                    created_at=datetime.combine(ob.due_date, datetime.min.time(), tzinfo=timezone.utc),
                )
            )
        elif is_in_alert_window(ob.due_date, ob.status, band):
            days = (ob.due_date - today()).days
            out.append(
                NotificationOut(
                    kind=NotificationKind.alert_window,
                    title=f"{ob.rule.form_name} entering alert window",
                    body=f"{ob.entity.name} · {days} day{'' if days == 1 else 's'} to file",
                    link_url=f"/obligations/{ob.id}",
                    obligation_id=ob.id,
                    read=False,
                    created_at=datetime.combine(ob.due_date, datetime.min.time(), tzinfo=timezone.utc),
                )
            )

    out.sort(key=lambda n: (n.read, -n.created_at.timestamp(), -(n.id or 0)))
    return out[:60]


class MarkReadRequest(BaseModel):
    ids: list[int]


@router.post("/read", status_code=204)
def mark_read(
    payload: MarkReadRequest,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    if not payload.ids:
        return
    db.execute(
        update(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.id.in_(payload.ids),
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(tz=timezone.utc))
    )
    db.commit()


@router.post("/read-all", status_code=204)
def mark_all_read(
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(tz=timezone.utc))
    )
    db.commit()


# ---------------------------------------------------------------------------
# Internal helpers — called from other API modules to emit notifications.
# ---------------------------------------------------------------------------
def emit_assignment(
    db: Session,
    *,
    assignee: User,
    obligation: Obligation,
    actor: User,
) -> None:
    """Persist an 'assigned' notification for the new assignee. No-op if the
    assignee just self-assigned (the typical mark-it-mine flow)."""
    if assignee.id == actor.id:
        return
    body = (
        f"{obligation.rule.form_name} — {obligation.entity.name}"
        if obligation.rule and obligation.entity
        else "Compliance item"
    )
    db.add(
        Notification(
            user_id=assignee.id,
            kind=NotificationKind.assigned,
            title=f"{actor.full_name or actor.email} assigned you a compliance item",
            body=body,
            link_url=f"/obligations/{obligation.id}",
            obligation_id=obligation.id,
            actor_id=actor.id,
        )
    )


# Match @<identifier>. We resolve against active users by:
#   - exact email match  (rare but supported)
#   - local-part match   (e.g. @pranav.goldar)
#   - first-name match   (e.g. @pranav)
_MENTION_RE = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9._+\-@]+)")


def extract_mentions(db: Session, body: str) -> list[User]:
    """Returns a de-duplicated list of active users mentioned in `body`."""
    tokens = {m.group(1).lower().rstrip(".") for m in _MENTION_RE.finditer(body or "")}
    if not tokens:
        return []

    users = db.execute(
        select(User).where(User.is_active.is_(True))
    ).scalars().all()

    found: dict[int, User] = {}
    for u in users:
        email_lc = u.email.lower()
        local = email_lc.split("@", 1)[0]
        first = (u.full_name or "").split(" ", 1)[0].lower()
        for token in tokens:
            if token == email_lc or token == local or token == first:
                found[u.id] = u
                break
    return list(found.values())


def emit_mentions(
    db: Session,
    *,
    mentions: list[User],
    actor: User,
    obligation: Obligation,
    comment_id: Optional[int],
    body: str,
) -> None:
    snippet = (body or "").strip()
    if len(snippet) > 240:
        snippet = snippet[:237] + "…"
    for u in mentions:
        if u.id == actor.id:
            continue
        db.add(
            Notification(
                user_id=u.id,
                kind=NotificationKind.mention,
                title=f"{actor.full_name or actor.email} mentioned you",
                body=snippet,
                link_url=f"/obligations/{obligation.id}",
                obligation_id=obligation.id,
                comment_id=comment_id,
                actor_id=actor.id,
            )
        )


def emit_status_change(
    db: Session,
    *,
    assignee: Optional[User],
    obligation: Obligation,
    new_status: ObligationStatus,
    actor: User,
) -> None:
    """Ping the assignee on terminal status transitions, when it isn't them
    making the change."""
    if assignee is None or assignee.id == actor.id:
        return
    if new_status not in (
        ObligationStatus.completed,
        ObligationStatus.pending_review,
    ):
        return
    label = {
        ObligationStatus.completed: "completed",
        ObligationStatus.pending_review: "moved to pending review",
    }[new_status]
    db.add(
        Notification(
            user_id=assignee.id,
            kind=NotificationKind.status_change,
            title=f"{actor.full_name or actor.email} {label} your item",
            body=(
                f"{obligation.rule.form_name} — {obligation.entity.name}"
                if obligation.rule and obligation.entity
                else None
            ),
            link_url=f"/obligations/{obligation.id}",
            obligation_id=obligation.id,
            actor_id=actor.id,
        )
    )
