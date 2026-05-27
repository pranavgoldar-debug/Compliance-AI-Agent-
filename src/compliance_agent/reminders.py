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
from compliance_agent.api._helpers import lead_time_days, reminder_offsets_days, today
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


def _build_email_body(obligation: Obligation, days_remaining: int) -> tuple[str, str]:
    rule = obligation.rule
    entity = obligation.entity
    form = rule.form_name if rule else "Compliance item"
    authority = rule.authority if rule else "—"
    entity_name = entity.name if entity else "—"
    subject = f"[Aspora] Reminder: {form} due in {days_remaining}d ({entity_name})"
    body = (
        f"Hi,\n\n"
        f"This is a deadline reminder from Aspora Compliance OS.\n\n"
        f"Filing:     {form}\n"
        f"Entity:     {entity_name}\n"
        f"Authority:  {authority}\n"
        f"Frequency:  {rule.frequency if rule else '—'}\n"
        f"Due date:   {obligation.due_date.isoformat()}  ({days_remaining} days)\n"
        f"Status:     {obligation.status.value if obligation.status else '—'}\n\n"
        f"Open it: /obligations/{obligation.id}\n\n"
        f"You're receiving this because you're the assignee. "
        f"Toggle reminders in Settings → Notifications.\n"
    )
    return subject, body


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

            subject, body = _build_email_body(ob, days_left)
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
