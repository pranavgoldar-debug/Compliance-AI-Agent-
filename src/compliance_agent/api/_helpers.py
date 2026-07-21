"""Internal helpers used across API route modules."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from compliance_agent.db import (
    Activity,
    EFFORT_BAND_DAYS,
    EffortBand,
    Entity,
    Obligation,
    ObligationStatus,
)
from compliance_agent.api.schemas import (
    CalendarObligation,
    EntityOut,
    ObligationOut,
    UserBrief,
)


# Fallback for legacy callers — alert lead time = 2× effort-band days.
ALERT_WINDOW_DAYS = 14


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def today() -> date:
    return now_utc().date()


def days_remaining(due: date) -> int:
    return (due - today()).days


def reminder_offsets_days(band: EffortBand) -> list[int]:
    """When to send reminders (days BEFORE due date). One entry per ping.

    Aspora policy:
      Monthly   (w1)  →  [7]              one reminder, a week before
      Quarterly (w2)  →  [25, 15]         two reminders, 25 and 15 days before
      Half-year (w4)  →  [30, 15]
      Annual    (w8)  →  [45, 30]         two reminders, 45 and 30 days before
      Long-form (w12) →  [60, 30]
    """
    return _REMINDER_OFFSETS.get(band, [30])


def lead_time_days(band: EffortBand) -> int:
    """Outer edge of the reminder window — used for the in-app
    "in alert" badge / dashboard count. Equals the earliest reminder
    offset for the band."""
    return max(reminder_offsets_days(band))


_REMINDER_OFFSETS: dict[EffortBand, list[int]] = {
    EffortBand.w1: [7],
    EffortBand.w2: [25, 15],
    EffortBand.w4: [30, 15],
    EffortBand.w8: [45, 30],
    EffortBand.w12: [60, 30],
}


def is_overdue(due: date, status: ObligationStatus) -> bool:
    return (
        due < today()
        and status not in (ObligationStatus.completed, ObligationStatus.not_applicable)
    )


def is_awaiting_payment(obligation: "Obligation") -> bool:
    """True when a filing is done but its payment leg is still open.
    Signals the compliance → finance hand-off point: status is completed,
    the rule has a payment_rule (money changes hands), but no payment
    reference has been logged yet."""
    rule = obligation.rule
    if rule is None or not (rule.payment_rule or "").strip():
        return False
    if obligation.status != ObligationStatus.completed:
        return False
    return not (obligation.payment_reference or "").strip()


def is_in_alert_window(
    due: date,
    status: ObligationStatus,
    band: EffortBand = EffortBand.w4,
) -> bool:
    d = days_remaining(due)
    return (
        0 <= d <= lead_time_days(band)
        and status not in (ObligationStatus.completed, ObligationStatus.not_applicable)
    )


def next_alert_date(due: date, band: EffortBand = EffortBand.w4) -> date:
    """The date the obligation enters its alert window."""
    return due - timedelta(days=lead_time_days(band))


def serialize_user(user) -> Optional[UserBrief]:
    if user is None:
        return None
    return UserBrief.model_validate(user)


def serialize_obligation(o: Obligation) -> ObligationOut:
    band = o.effort_band or EffortBand.w4
    return ObligationOut(
        id=o.id,
        rule_id=o.rule_id,
        entity_id=o.entity_id,
        rule_name=o.rule.name,
        rule_form_name=o.rule.form_name,
        rule_authority=o.rule.authority,
        rule_category=o.rule.category,
        rule_frequency=o.rule.frequency,
        rule_due_date_rule=o.rule.due_date_rule,
        rule_source_url=o.rule.source_url,
        rule_submission_url=o.rule.submission_url,
        rule_source_changed_at=o.rule.source_changed_at,
        rule_payment_rule=o.rule.payment_rule,
        entity_name=o.entity.name,
        entity_jurisdiction_code=o.entity.jurisdiction_code,
        due_date=o.due_date,
        period_label=o.period_label,
        status=o.status,
        department=(o.department.value if o.department else "compliance"),
        assignee=serialize_user(o.assignee),
        effort_band=band,
        effort_band_reason=o.effort_band_reason,
        filing_reference=o.filing_reference,
        payment_amount=o.payment_amount,
        payment_reference=o.payment_reference,
        beneficiary_details=o.beneficiary_details,
        is_awaiting_payment=is_awaiting_payment(o),
        notes=o.notes,
        days_remaining=days_remaining(o.due_date),
        is_overdue=is_overdue(o.due_date, o.status),
        is_in_alert_window=is_in_alert_window(o.due_date, o.status, band),
        next_alert_at=next_alert_date(o.due_date, band),
        completed_at=o.completed_at,
        created_at=o.created_at,
        updated_at=o.updated_at,
    )


def serialize_calendar_obligation(o: Obligation) -> CalendarObligation:
    band = o.effort_band or EffortBand.w4
    return CalendarObligation(
        id=o.id,
        due_date=o.due_date,
        status=o.status,
        entity_id=o.entity_id,
        entity_name=o.entity.name,
        entity_jurisdiction_code=o.entity.jurisdiction_code,
        rule_form_name=o.rule.form_name,
        rule_authority=o.rule.authority,
        rule_category=o.rule.category,
        rule_applicability=(
            o.rule.applicability.value if o.rule.applicability else "Mandatory"
        ),
        effort_band=band,
        assignee=serialize_user(o.assignee),
        is_overdue=is_overdue(o.due_date, o.status),
        is_in_alert_window=is_in_alert_window(o.due_date, o.status, band),
        days_remaining=days_remaining(o.due_date),
    )


def serialize_entity(entity: Entity, db: Session) -> EntityOut:
    """Compute the obligation counts inline so the entity card shows real stats."""
    counts = db.execute(
        select(
            func.count(Obligation.id).filter(
                Obligation.status.notin_(
                    [ObligationStatus.completed, ObligationStatus.not_applicable]
                )
            ).label("active"),
            func.count(Obligation.id).filter(
                Obligation.due_date < today(),
                Obligation.status.notin_(
                    [ObligationStatus.completed, ObligationStatus.not_applicable]
                ),
            ).label("overdue"),
            func.count(Obligation.id).filter(
                Obligation.due_date >= today(),
                Obligation.due_date <= today().replace(day=today().day),  # placeholder
                Obligation.status.notin_(
                    [ObligationStatus.completed, ObligationStatus.not_applicable]
                ),
            ).label("alert"),
        ).where(Obligation.entity_id == entity.id)
    ).one()

    # Replace the broken alert-window count above with a clean recompute.
    from datetime import timedelta

    active = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.entity_id == entity.id,
            Obligation.status.notin_(
                [ObligationStatus.completed, ObligationStatus.not_applicable]
            ),
        )
    ).scalar_one()
    overdue = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.entity_id == entity.id,
            Obligation.due_date < today(),
            Obligation.status.notin_(
                [ObligationStatus.completed, ObligationStatus.not_applicable]
            ),
        )
    ).scalar_one()
    alert = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.entity_id == entity.id,
            Obligation.due_date >= today(),
            Obligation.due_date <= today() + timedelta(days=ALERT_WINDOW_DAYS),
            Obligation.status.notin_(
                [ObligationStatus.completed, ObligationStatus.not_applicable]
            ),
        )
    ).scalar_one()
    last_filed = db.execute(
        select(func.max(Obligation.completed_at)).where(
            Obligation.entity_id == entity.id,
            Obligation.completed_at.isnot(None),
        )
    ).scalar_one()

    return EntityOut(
        id=entity.id,
        name=entity.name,
        legal_type=entity.legal_type,
        jurisdiction_code=entity.jurisdiction_code,
        short_code=entity.short_code,
        registration_number=entity.registration_number,
        incorporation_date=entity.incorporation_date,
        fiscal_year_end=entity.fiscal_year_end,
        country_lead=serialize_user(entity.country_lead),
        archived_at=entity.archived_at,
        created_at=entity.created_at,
        active_obligations_count=active,
        overdue_obligations_count=overdue,
        in_alert_window_count=alert,
        last_filed_at=last_filed,
    )


def log_activity(
    db: Session,
    *,
    actor_id: Optional[int],
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    payload: Optional[dict] = None,
) -> None:
    db.add(
        Activity(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            payload=payload,
        )
    )
