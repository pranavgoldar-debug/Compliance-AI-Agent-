"""Dashboard endpoint — counters and the three lists shown on the home page."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from compliance_agent.api._helpers import (
    ALERT_WINDOW_DAYS,
    serialize_obligation,
    today,
)
from compliance_agent.api.schemas import DashboardStats
from compliance_agent.auth import get_current_user
from compliance_agent.classification import FINANCE_ONLY, keep_function
from compliance_agent.db import (
    Entity,
    License,
    Obligation,
    ObligationStatus,
    Rule,
    User,
    get_session,
)


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _eager():
    return [
        joinedload(Obligation.rule),
        joinedload(Obligation.entity),
        joinedload(Obligation.assignee),
    ]


@router.get("", response_model=DashboardStats)
def dashboard(
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DashboardStats:
    open_statuses = [ObligationStatus.not_started, ObligationStatus.in_progress, ObligationStatus.pending_review]

    # FINANCE_ONLY switch: every counter / list below is scoped to obligations
    # whose rule belongs to the Finance function. `fin` is an extra WHERE
    # clause (empty when the switch is off, so the full set shows).
    # Exclude obligations of archived entities from every dashboard counter and
    # list below (archiving an entity archives its filings off the dashboard).
    fin: list = [Obligation.entity.has(Entity.archived_at.is_(None))]
    if FINANCE_ONLY:
        allowed_rule_ids = [
            r.id
            for r in db.execute(select(Rule)).scalars().all()
            if keep_function(r.category, r.area, r.responsible_function)
        ]
        fin = [Obligation.rule_id.in_(allowed_rule_ids)]

    overdue = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.due_date < today(),
            Obligation.status.in_(open_statuses),
            *fin,
        )
    ).scalar_one()

    in_alert = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.due_date >= today(),
            Obligation.due_date <= today() + timedelta(days=ALERT_WINDOW_DAYS),
            Obligation.status.in_(open_statuses),
            *fin,
        )
    ).scalar_one()

    safe = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.due_date > today() + timedelta(days=ALERT_WINDOW_DAYS),
            Obligation.status.in_(open_statuses),
            *fin,
        )
    ).scalar_one()

    first_of_month = today().replace(day=1)
    completed_this_month = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.status == ObligationStatus.completed,
            Obligation.completed_at >= first_of_month,
            *fin,
        )
    ).scalar_one()

    week_end_d = today() + timedelta(days=7)
    due_this_week = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.due_date >= today(),
            Obligation.due_date <= week_end_d,
            Obligation.status.in_(open_statuses),
            *fin,
        )
    ).scalar_one()

    # End of current month — simple inclusive cap.
    if today().month == 12:
        next_month_start = today().replace(year=today().year + 1, month=1, day=1)
    else:
        next_month_start = today().replace(month=today().month + 1, day=1)
    month_end = next_month_start - timedelta(days=1)
    due_this_month = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.due_date >= today(),
            Obligation.due_date <= month_end,
            Obligation.status.in_(open_statuses),
            *fin,
        )
    ).scalar_one()

    unassigned = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.assignee_id.is_(None),
            Obligation.status.in_(open_statuses),
            *fin,
        )
    ).scalar_one()

    # Active entities + uploaded licenses — at-a-glance footprint on the
    # dashboard so the team can see the size of what they're managing.
    entity_count = db.execute(
        select(func.count(Entity.id)).where(Entity.archived_at.is_(None))
    ).scalar_one()

    license_count = db.execute(select(func.count(License.id))).scalar_one()

    # Items the assignee has submitted but admin hasn't approved yet —
    # drives the "Awaiting your review" affordance for admins.
    awaiting_review = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.status == ObligationStatus.pending_review,
            *fin,
        )
    ).scalar_one()

    # Compliance → finance hand-off queue: filing done, payment still owed.
    # Computed in Python because the "rule has payment_rule" check joins on
    # a text column that's expensive to express as a single SQL aggregate.
    completed_with_payment_rule = db.execute(
        select(Obligation)
        .where(Obligation.status == ObligationStatus.completed, *fin)
        .options(joinedload(Obligation.rule))
    ).scalars().unique().all()
    awaiting_payment = sum(
        1
        for o in completed_with_payment_rule
        if o.rule
        and (o.rule.payment_rule or "").strip()
        and not (o.payment_reference or "").strip()
    )

    open_tasks = db.execute(
        select(Obligation)
        .where(Obligation.assignee_id == user.id, Obligation.status.in_(open_statuses), *fin)
        .options(*_eager())
        .order_by(Obligation.due_date.asc())
        .limit(20)
    ).scalars().unique().all()

    in_alert_items = db.execute(
        select(Obligation)
        .where(
            Obligation.due_date >= today(),
            Obligation.due_date <= today() + timedelta(days=ALERT_WINDOW_DAYS),
            Obligation.status.in_(open_statuses),
            *fin,
        )
        .options(*_eager())
        .order_by(Obligation.due_date.asc())
        .limit(20)
    ).scalars().unique().all()

    week_end = today() + timedelta(days=7)
    this_week = db.execute(
        select(Obligation)
        .where(Obligation.due_date >= today(), Obligation.due_date <= week_end, *fin)
        .options(*_eager())
        .order_by(Obligation.due_date.asc())
    ).scalars().unique().all()

    return DashboardStats(
        overdue=overdue,
        in_alert_window=in_alert,
        in_safe_zone=safe,
        completed_this_month=completed_this_month,
        due_this_week=due_this_week,
        due_this_month=due_this_month,
        unassigned=unassigned,
        entity_count=entity_count,
        license_count=license_count,
        awaiting_review=awaiting_review,
        awaiting_payment=awaiting_payment,
        open_tasks=[serialize_obligation(o) for o in open_tasks],
        items_in_alert_window=[serialize_obligation(o) for o in in_alert_items],
        this_week=[serialize_obligation(o) for o in this_week],
    )
