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

from compliance_agent import slack_service
from compliance_agent.api._helpers import is_in_alert_window, is_overdue, serialize_user, today
from compliance_agent.api.schemas import UserBrief
from compliance_agent.auth import get_current_user
from compliance_agent.db import (
    Department,
    EffortBand,
    Notification,
    NotificationKind,
    Obligation,
    ObligationStatus,
    User,
    get_session,
)
from compliance_agent.email_service import base_url, send_email, smtp_configured


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
    assignee just self-assigned (the typical mark-it-mine flow). Also pings
    Slack (channel-wide) when the workspace has a webhook and the assignee
    has notify_slack enabled."""
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
    # Side-channel fan-out (best-effort, never raises).
    if assignee.notify_slack and slack_service.is_configured(db):
        slack_service.post(
            slack_service.assignment_message(
                obligation=obligation, assignee=assignee, actor=actor
            )
        )

    # Email the assignee (when they have email alerts on + SMTP is set up).
    if assignee.notify_email and smtp_configured():
        link = f"{base_url().rstrip('/')}/obligations/{obligation.id}"
        try:
            send_email(
                to=assignee.email,
                subject=f"Assigned: {body}",
                body_text=(
                    f"{actor.full_name or actor.email} assigned you a compliance item.\n\n"
                    f"{body}\n"
                    f"Due: {obligation.due_date.isoformat()}\n\n"
                    f"Open it: {link}"
                ),
                body_html=(
                    f"<p><strong>{actor.full_name or actor.email}</strong> assigned you "
                    f"a compliance item.</p>"
                    f"<p>{body}<br/>Due: {obligation.due_date.isoformat()}</p>"
                    f'<p><a href="{link}">Open in Compliance OS</a></p>'
                ),
            )
        except Exception:  # noqa: BLE001 — never block the assignment on email
            pass

    # Finance hand-off via ClickUp: if the assignee is on the finance team and
    # ClickUp is connected, drop a task so they can action it there. Guarded on
    # clickup_task_id so we never create a duplicate (the payment-request flow
    # may already have made one).
    if (
        assignee.department == Department.finance
        and not obligation.clickup_task_id
    ):
        from compliance_agent import clickup_service

        if clickup_service.is_configured(db):
            created = clickup_service.create_payment_task(
                db,
                obligation,
                amount=obligation.payment_amount or "—",
                notes=f"Assigned to {assignee.full_name or assignee.email}.",
                app_url=base_url(),
            )
            if created:
                obligation.clickup_task_id, obligation.clickup_task_url = created


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
    slack_on = slack_service.is_configured(db)
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
        if u.notify_slack and slack_on:
            slack_service.post(
                slack_service.mention_message(
                    obligation=obligation, mentioned=u, actor=actor, body=body
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
    """Notify the right people on terminal status transitions:
      - completed       → ping the assignee (if not them)
      - pending_review  → ping ALL admins (their queue) + the assignee
    """
    if new_status not in (
        ObligationStatus.completed,
        ObligationStatus.pending_review,
    ):
        return
    label = {
        ObligationStatus.completed: "completed",
        ObligationStatus.pending_review: "submitted for review",
    }[new_status]
    body = (
        f"{obligation.rule.form_name} — {obligation.entity.name}"
        if obligation.rule and obligation.entity
        else None
    )

    # 1. Ping the assignee (if they didn't make the change themselves).
    if assignee is not None and assignee.id != actor.id:
        db.add(
            Notification(
                user_id=assignee.id,
                kind=NotificationKind.status_change,
                title=f"{actor.full_name or actor.email} {label} your item",
                body=body,
                link_url=f"/obligations/{obligation.id}",
                obligation_id=obligation.id,
                actor_id=actor.id,
            )
        )

    # 2. On pending_review, also wake up every admin so the verification
    # queue gets attention. Don't ping the actor (they just submitted it).
    if new_status == ObligationStatus.pending_review:
        from compliance_agent.db import Role

        admins = (
            db.execute(
                select(User).where(User.role == Role.admin, User.is_active.is_(True))
            )
            .scalars()
            .all()
        )
        for admin in admins:
            if admin.id == actor.id:
                continue
            db.add(
                Notification(
                    user_id=admin.id,
                    kind=NotificationKind.status_change,
                    title=f"{actor.full_name or actor.email} submitted for review",
                    body=body,
                    link_url=f"/obligations/{obligation.id}",
                    obligation_id=obligation.id,
                    actor_id=actor.id,
                )
            )

        # Slack ping for the workspace channel on submit-for-review too.
        if slack_service.is_configured(db):
            form = obligation.rule.form_name if obligation.rule else "Compliance item"
            entity = obligation.entity.name if obligation.entity else "—"
            slack_service.post(
                f":eyes: *{form}* ({entity}) submitted for review by "
                f"{actor.full_name or actor.email} — admins, please verify."
            )

    # Slack: channel-wide "marked filed" for completed transitions.
    if (
        new_status == ObligationStatus.completed
        and assignee is not None
        and assignee.notify_slack
        and slack_service.is_configured(db)
    ):
        slack_service.post(
            slack_service.filed_message(obligation=obligation, actor=actor)
        )
