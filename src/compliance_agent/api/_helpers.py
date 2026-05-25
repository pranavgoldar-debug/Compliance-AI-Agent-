"""Internal helpers used across API route modules."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from compliance_agent.db import Activity, Entity, Obligation, ObligationStatus
from compliance_agent.api.schemas import (
    CalendarObligation,
    EntityOut,
    ObligationOut,
    UserBrief,
)


ALERT_WINDOW_DAYS = 14  # days-until-due that flag "in alert window"


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def today() -> date:
    return now_utc().date()


def days_remaining(due: date) -> int:
    return (due - today()).days


def is_overdue(due: date, status: ObligationStatus) -> bool:
    return (
        due < today()
        and status not in (ObligationStatus.completed, ObligationStatus.not_applicable)
    )


def is_in_alert_window(due: date, status: ObligationStatus) -> bool:
    d = days_remaining(due)
    return (
        0 <= d <= ALERT_WINDOW_DAYS
        and status not in (ObligationStatus.completed, ObligationStatus.not_applicable)
    )


def serialize_user(user) -> Optional[UserBrief]:
    if user is None:
        return None
    return UserBrief.model_validate(user)


def serialize_obligation(o: Obligation) -> ObligationOut:
    return ObligationOut(
        id=o.id,
        rule_id=o.rule_id,
        entity_id=o.entity_id,
        rule_name=o.rule.name,
        rule_form_name=o.rule.form_name,
        rule_authority=o.rule.authority,
        rule_category=o.rule.category,
        rule_frequency=o.rule.frequency,
        entity_name=o.entity.name,
        entity_jurisdiction_code=o.entity.jurisdiction_code,
        due_date=o.due_date,
        period_label=o.period_label,
        status=o.status,
        assignee=serialize_user(o.assignee),
        filing_reference=o.filing_reference,
        payment_amount=o.payment_amount,
        payment_reference=o.payment_reference,
        notes=o.notes,
        days_remaining=days_remaining(o.due_date),
        is_overdue=is_overdue(o.due_date, o.status),
        is_in_alert_window=is_in_alert_window(o.due_date, o.status),
        completed_at=o.completed_at,
        created_at=o.created_at,
        updated_at=o.updated_at,
    )


def serialize_calendar_obligation(o: Obligation) -> CalendarObligation:
    return CalendarObligation(
        id=o.id,
        due_date=o.due_date,
        status=o.status,
        entity_id=o.entity_id,
        entity_name=o.entity.name,
        rule_form_name=o.rule.form_name,
        rule_authority=o.rule.authority,
        rule_category=o.rule.category,
        is_overdue=is_overdue(o.due_date, o.status),
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
