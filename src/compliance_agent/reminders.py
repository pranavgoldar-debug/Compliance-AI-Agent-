"""Outbound deadline reminders.

The FIRST reminder for each open assigned obligation is driven by the
filing's frequency (reminder_offsets_for_frequency), and the follow-up
cadence escalates per frequency until the filing is Filed:

  Monthly      →  first at  7 days before, then DAILY
  Quarterly    →  first at 30 days before, then every 2 days
  Half-yearly  →  first at 45 days before, then weekly
  Annual       →  first at 60 days before, then weekly until T-14,
                  daily after
  Multi-year   →  first at 90 days before, then bi-weekly until T-28,
                  weekly after

Every filing also gets a "due today" ping on the due date itself, and
once overdue, a chaser every 7 days late (7, 14, 21, …).

Intended to be run on a daily schedule:

  python -m compliance_agent.cli send-reminders          # actually send
  python -m compliance_agent.cli send-reminders --dry-run

Idempotent — each (assignee, obligation, slot) fires exactly once.
A Notification row with the slot tag baked into its title is the dedup
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
    obligation_status_label,
    session_scope,
)
from compliance_agent.email_service import send_email


# Markers baked into Notification.title so cron runs can dedup per-slot
# without needing a new column. T-N = N days before due, T+N = N days late.
_OFFSET_TAG = "[T-{}d]"
_OVERDUE_TAG = "[T+{}d]"


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
    status = obligation_status_label(obligation.status)
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


def _already_reminded(
    db: Session,
    user_id: int,
    obligation_id: int,
    tag: str,
) -> bool:
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
    """All open, assigned obligations — including overdue ones, which keep
    getting chased weekly until they're filed. The caller decides which
    reminder slot (if any) fires today."""
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
            Obligation.assignee_id.is_not(None),
        )
        .order_by(Obligation.due_date)
    )
    return db.execute(stmt).scalars().unique().all()


def _reminder_slots(lead: int) -> list[int]:
    """All pre-due reminder days for a filing — the frequency lead itself,
    then the per-frequency escalation ladder down to (and including) the
    due date:

      lead ≤ 7  (Monthly)     → daily:            [7, 6, 5, 4, 3, 2, 1, 0]
      lead ≤ 30 (Quarterly)   → every 2 days:     [30, 28, 26, …, 2, 0]
      lead ≤ 45 (Half-yearly) → weekly:           [45, 38, 31, 24, 17, 10, 3, 0]
      lead ≤ 60 (Annual)      → weekly to T-14,
                                daily after:      [60, 53, …, 18, 14, 13, …, 0]
      lead > 60 (Multi-year)  → bi-weekly to T-28,
                                weekly after:     [90, 76, 62, 48, 34, 28, 21, 14, 7, 0]
    """
    if lead <= 7:
        slots = list(range(lead, -1, -1))
    elif lead <= 30:
        slots = list(range(lead, -1, -2))
    elif lead <= 45:
        slots = list(range(lead, -1, -7))
    elif lead <= 60:
        slots = list(range(lead, 14, -7)) + list(range(14, -1, -1))
    else:
        slots = list(range(lead, 28, -14)) + list(range(28, -1, -7))
    if 0 not in slots:
        slots.append(0)
    return sorted(set(slots), reverse=True)


def _trigger_offset(
    offsets: list[int],
    days_left: int,
) -> Optional[int]:
    """Pick the pre-due slot that fires today.

    Fires when days_left is at-or-just-passed a slot boundary AND we
    haven't passed the next (smaller) slot yet. In practice that means
    the cron run that lands on or first dips below a slot triggers it.

    Examples for slots [30, 23, 16, 9, 2, 0]:
       days_left=31 → returns None  (not in any window yet)
       days_left=30 → returns 30    (entering the 30-day window)
       days_left=27 → returns 30    (still in the 30 slot — dedups, no send)
       days_left=23 → returns 23    (weekly follow-up)
       days_left=0  → returns 0     (due today)

    The de-dup check in send_reminders handles the "fire only once" part;
    this function just routes today's run to the right slot bucket.
    """
    candidates = [o for o in offsets if days_left <= o]
    if not candidates:
        return None
    # Tightest (smallest) slot that still applies — so once we cross the
    # next weekly boundary, future runs route to that slot, not the old one.
    return min(candidates)


def send_reminders(*, dry_run: bool = False) -> list[ReminderResult]:
    """Walk every open assigned obligation, decide which reminder offset
    (if any) fires today, and send / dedup accordingly."""
    results: list[ReminderResult] = []
    today_d = today()

    with session_scope() as db:
        slack_on = slack_service.is_configured(db)

        for ob in find_due_for_reminder(db):
            # The FIRST reminder is driven by the filing's FREQUENCY
            # (Monthly→7d, Quarterly→30d, Half-yearly→45d, Annual→60d,
            # Multi-year→90d); fall back to the effort-band offsets when
            # the rule has no usable frequency. After that the per-frequency
            # escalation ladder (_reminder_slots) runs to the due date,
            # then weekly overdue pings.
            freq = ob.rule.frequency if ob.rule else ""
            offsets = reminder_offsets_for_frequency(freq)
            if not offsets:
                band = ob.effort_band or EffortBand.w4
                offsets = reminder_offsets_days(band)
            if not offsets:
                continue
            days_left = (ob.due_date - today_d).days

            if days_left >= 0:
                offset = _trigger_offset(_reminder_slots(max(offsets)), days_left)
                if offset is None:
                    continue
                tag = _OFFSET_TAG.format(offset)
            else:
                # Overdue — chase every 7 days late (the due-day ping covers
                # days 1–6 late via its own dedup slot).
                days_late = -days_left
                late_slot = (days_late // 7) * 7
                if late_slot == 0:
                    continue
                offset = -late_slot
                tag = _OVERDUE_TAG.format(late_slot)

            assignee: Optional[User] = ob.assignee
            if assignee is None or not assignee.is_active:
                continue
            if _already_reminded(db, assignee.id, ob.id, tag):
                continue

            subject, body, body_html = _build_email_body(db, ob, days_left)
            email_sent = False
            slack_sent = False

            if not dry_run:
                form = ob.rule.form_name if ob.rule else "Compliance item"
                title = (
                    f"Reminder {tag}: {form} due in {days_left}d"
                    if days_left >= 0
                    else f"Overdue {tag}: {form} — {-days_left}d late"
                )
                db.add(
                    Notification(
                        user_id=assignee.id,
                        kind=NotificationKind.alert_window,
                        title=title,
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
                    if days_left >= 0:
                        msg = slack_service.deadline_blocks(
                            obligation=ob, assignee=assignee, days_remaining=days_left
                        )
                    else:
                        msg = slack_service.overdue_blocks(
                            obligation=ob, days_late=-days_left
                        )
                    slack_sent = bool(
                        slack_service.post(
                            msg["text"],
                            blocks=msg["blocks"],
                            sync=True,
                            function=(ob.rule.responsible_function if ob.rule else None),
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
