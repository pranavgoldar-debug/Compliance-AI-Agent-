"""Outbound deadline reminders.

When an obligation enters its alert window (computed from its effort band
via `lead_time_days`), send the assignee a one-time email + Slack ping
and persist an `alert_window` notification so the in-app bell shows it
and so subsequent CLI runs don't re-send.

Intended to be run on a daily schedule:

  python -m compliance_agent.cli send-reminders          # actually send
  python -m compliance_agent.cli send-reminders --dry-run

Idempotent: dedup key is (user_id, kind=alert_window, obligation_id).
Once a reminder Notification row exists for a given user + obligation we
never resend, even across runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from compliance_agent import slack_service
from compliance_agent.api._helpers import lead_time_days, today
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


@dataclass
class ReminderResult:
    obligation_id: int
    assignee_email: str
    days_remaining: int
    email_sent: bool
    slack_sent: bool


def _frequency_phrase(band: EffortBand, days: int) -> str:
    """Human-readable cadence so the email subject matches policy."""
    if band == EffortBand.w1:
        return "weekly filing — due in a week"
    if band == EffortBand.w2:
        return f"quarterly filing — due in {days} days"
    if band == EffortBand.w8:
        return f"annual filing — due in {days} days"
    return f"due in {days} days"


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


def _already_reminded(db: Session, user_id: int, obligation_id: int) -> bool:
    return (
        db.execute(
            select(Notification.id).where(
                Notification.user_id == user_id,
                Notification.kind == NotificationKind.alert_window,
                Notification.obligation_id == obligation_id,
            ).limit(1)
        ).scalar_one_or_none()
        is not None
    )


def find_due_for_reminder(db: Session) -> list[Obligation]:
    """All open, assigned obligations whose due_date is between today and
    today + lead_time_days(band). The caller filters out ones we've already
    reminded about."""
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


def send_reminders(*, dry_run: bool = False) -> list[ReminderResult]:
    """Send a reminder for every open assigned obligation inside its
    alert window that we haven't already reminded about."""
    results: list[ReminderResult] = []
    today_d = today()

    with session_scope() as db:
        slack_on = slack_service.is_configured(db)

        for ob in find_due_for_reminder(db):
            band = ob.effort_band or EffortBand.w4
            lead = lead_time_days(band)
            days_left = (ob.due_date - today_d).days
            if days_left > lead:
                # Not yet in the alert window for this band.
                continue

            assignee: Optional[User] = ob.assignee
            if assignee is None:
                continue
            if _already_reminded(db, assignee.id, ob.id):
                continue

            subject, body = _build_email_body(ob, days_left)
            email_sent = False
            slack_sent = False

            if not dry_run:
                # Persist the in-app notification first — that's also our
                # idempotency anchor for the next CLI run.
                db.add(
                    Notification(
                        user_id=assignee.id,
                        kind=NotificationKind.alert_window,
                        title=f"Reminder: {ob.rule.form_name if ob.rule else 'Compliance item'} due in {days_left}d",
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
                    email_sent=email_sent,
                    slack_sent=slack_sent,
                )
            )

        # Commit all the new Notification rows in one go.
        if not dry_run and results:
            db.commit()

    return results
