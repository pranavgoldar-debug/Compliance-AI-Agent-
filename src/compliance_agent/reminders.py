"""Outbound deadline reminders.

For each open assigned obligation, we send a reminder when its
days-remaining hits one of the offsets defined per effort band in
`reminder_offsets_days()`. Aspora policy:

  Monthly   →  7 days before              (one ping)
  Quarterly →  25 and 15 days before      (two pings)
  Annual    →  45 and 30 days before      (two pings)

Intended to be run on a daily schedule:

  python -m compliance_agent.cli send-reminders          # actually send
  python -m compliance_agent.cli send-reminders --dry-run

Idempotent — each (assignee, obligation, offset) fires exactly once.
A Notification row with the offset baked into its title is the dedup
anchor, so cron runs never double-send.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from compliance_agent import slack_service
from compliance_agent.api._helpers import (
    lead_time_days,
    reminder_offsets_days,
    reminder_offsets_for_frequency,
    today,
)
from compliance_agent.db import (
    EffortBand,
    Notification,
    NotificationKind,
    Obligation,
    ObligationStatus,
    User,
    session_scope,
)
from compliance_agent.email_service import send_email


# Marker baked into Notification.title so cron runs can dedup per-offset
# without needing a new column.
_OFFSET_TAG = "[T-{}d]"


@dataclass
class ReminderResult:
    obligation_id: int
    assignee_email: str
    days_remaining: int
    offset_days: int
    email_sent: bool
    slack_sent: bool


def _assigner_name(db: Session, obligation: Obligation) -> str:
    """Who assigned this filing — named in the escalation line ('… {name} is
    copied automatically'). Resolved from the latest 'assigned' notification's
    actor, falling back to the rule's approver, then a generic phrase."""
    actor_id = db.execute(
        select(Notification.actor_id)
        .where(
            Notification.obligation_id == obligation.id,
            Notification.kind == NotificationKind.assigned,
            Notification.actor_id.is_not(None),
        )
        .order_by(Notification.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if actor_id is None and obligation.rule is not None:
        actor_id = obligation.rule.approver_id
    if actor_id:
        user = db.get(User, actor_id)
        if user is not None:
            return user.full_name or user.email
    return "your manager"


def _build_email_body(db: Session, obligation: Obligation, days_remaining: int) -> tuple[str, str, str]:
    """(subject, text, html) for the branded deadline-alert template."""
    from compliance_agent.email_service import base_url
    from compliance_agent.email_templates import deadline_alert_email

    rule = obligation.rule
    entity = obligation.entity
    assignee = obligation.assignee
    form = rule.form_name if rule else "Compliance item"
    status = (obligation.status.value if obligation.status else "—").replace("_", " ").title()
    updated = getattr(obligation, "updated_at", None)
    return deadline_alert_email(
        owner_name=(
            (assignee.full_name or assignee.email.split("@")[0]) if assignee else "there"
        ),
        obligation_name=form,
        days_remaining=days_remaining,
        due_date=obligation.due_date,
        regulator_name=(rule.authority if rule else "—") or "—",
        jurisdiction=(rule.jurisdiction_code if rule else "—").upper(),
        form_code=form,
        entity_name=entity.name if entity else "—",
        entity_ref=(getattr(entity, "short_code", None) or f"#{entity.id}") if entity else "—",
        obligation_type=(rule.category if rule else "—") or "—",
        frequency=(rule.frequency if rule else "—") or "—",
        period_covered=obligation.period_label or "—",
        status=status,
        last_action="status update",
        last_action_date=updated.date().isoformat() if updated else "—",
        open_url=f"{base_url().rstrip('/')}/obligations/{obligation.id}",
        escalation_contact_name=_assigner_name(db, obligation),
    )


def _slack_text(obligation: Obligation, assignee: User, days_remaining: int) -> str:
    form = obligation.rule.form_name if obligation.rule else "Compliance item"
    entity = obligation.entity.name if obligation.entity else "—"
    handle = (
        f"<@{assignee.slack_user_id}>"
        if getattr(assignee, "slack_user_id", None)
        else (assignee.full_name or assignee.email)
    )
    return (
        f":alarm_clock: Reminder — {handle} *{form}* ({entity}) "
        f"is due `{obligation.due_date.isoformat()}` "
        f"({days_remaining} day{'s' if days_remaining != 1 else ''} from now)."
    )


def _already_reminded_at_offset(
    db: Session,
    user_id: int,
    obligation_id: int,
    offset_days: int,
) -> bool:
    tag = _OFFSET_TAG.format(offset_days)
    return (
        db.execute(
            select(Notification.id)
            .where(
                Notification.user_id == user_id,
                Notification.kind == NotificationKind.alert_window,
                Notification.obligation_id == obligation_id,
                Notification.title.contains(tag),
            )
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


def find_due_for_reminder(db: Session) -> list[Obligation]:
    """All open, assigned, future obligations. The caller filters which
    offsets apply per-band."""
    today_d = today()
    stmt = (
        select(Obligation)
        .options(
            joinedload(Obligation.rule),
            joinedload(Obligation.entity),
            joinedload(Obligation.assignee),
        )
        .where(
            Obligation.status.in_(
                [
                    ObligationStatus.not_started,
                    ObligationStatus.in_progress,
                    ObligationStatus.pending_review,
                ]
            ),
            Obligation.due_date >= today_d,
            Obligation.assignee_id.is_not(None),
        )
        .order_by(Obligation.due_date)
    )
    return db.execute(stmt).scalars().unique().all()


def _trigger_offset(
    offsets: list[int],
    days_left: int,
) -> Optional[int]:
    """Pick the offset that fires today.

    Fires when days_left is at-or-just-passed an offset boundary AND we
    haven't passed the next (smaller) offset yet. In practice that means
    the cron run that lands on or first dips below an offset triggers it.

    Examples for annual offsets [45, 30]:
       days_left=46 → returns None  (not in any window yet)
       days_left=45 → returns 45    (entering 45-day window)
       days_left=40 → returns 45    (still in 45-day window, will dedup
                                      against existing 45d notification)
       days_left=30 → returns 30    (entering 30-day window)
       days_left=10 → returns 30    (still under 30d, dedup against 30d)

    The de-dup check in send_reminders handles the "fire only once" part;
    this function just routes today's run to the right offset bucket.
    """
    candidates = [o for o in offsets if days_left <= o]
    if not candidates:
        return None
    # Tightest (smallest) offset that still applies — so once we cross
    # 30 days for an annual, future runs route to the 30d slot, not 45d.
    return min(candidates)


def send_reminders(*, dry_run: bool = False) -> list[ReminderResult]:
    """Walk every open assigned obligation, decide which reminder offset
    (if any) fires today, and send / dedup accordingly."""
    results: list[ReminderResult] = []
    today_d = today()

    with session_scope() as db:
        slack_on = slack_service.is_configured(db)

        for ob in find_due_for_reminder(db):
            # Reminder cadence is driven by the filing's FREQUENCY (Monthly→7d,
            # Quarterly→30d, Annual→45d); fall back to the effort-band offsets
            # when the rule has no usable frequency.
            freq = ob.rule.frequency if ob.rule else ""
            offsets = reminder_offsets_for_frequency(freq)
            if not offsets:
                band = ob.effort_band or EffortBand.w4
                offsets = reminder_offsets_days(band)
            days_left = (ob.due_date - today_d).days

            offset = _trigger_offset(offsets, days_left)
            if offset is None:
                continue

            assignee: Optional[User] = ob.assignee
            if assignee is None:
                continue
            if _already_reminded_at_offset(db, assignee.id, ob.id, offset):
                continue

            subject, body, body_html = _build_email_body(db, ob, days_left)
            email_sent = False
            slack_sent = False

            if not dry_run:
                form = ob.rule.form_name if ob.rule else "Compliance item"
                db.add(
                    Notification(
                        user_id=assignee.id,
                        kind=NotificationKind.alert_window,
                        title=f"Reminder {_OFFSET_TAG.format(offset)}: {form} due in {days_left}d",
                        body=(ob.entity.name if ob.entity else None),
                        link_url=f"/obligations/{ob.id}",
                        obligation_id=ob.id,
                    )
                )

                if assignee.notify_email and assignee.email:
                    email_sent = send_email(
                        to=assignee.email,
                        subject=subject,
                        body_text=body,
                        body_html=body_html,
                    )

                if (
                    assignee.notify_slack
                    and slack_on
                    and slack_service.is_configured(db)
                ):
                    slack_sent = bool(
                        slack_service.post(
                            _slack_text(ob, assignee, days_left)
                        )
                    )

            results.append(
                ReminderResult(
                    obligation_id=ob.id,
                    assignee_email=assignee.email,
                    days_remaining=days_left,
                    offset_days=offset,
                    email_sent=email_sent,
                    slack_sent=slack_sent,
                )
            )

        if not dry_run and results:
            db.commit()

    return results


# Re-exported for tests / callers that need the outer-edge of the window
# (also drives the in-app "in alert window" badge via api/_helpers.py).
__all__ = ["send_reminders", "ReminderResult", "lead_time_days"]
