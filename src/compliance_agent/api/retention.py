"""Audit log retention — admin endpoint to purge old activity rows.

Triggered on demand by an admin. Default retention is 365 days (configurable
via COMPLIANCE_AUDIT_RETENTION_DAYS env var). We never auto-run this on a
schedule because the destructive action benefits from human approval.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from compliance_agent.auth import require_admin
from compliance_agent.db import Activity, User, get_session


router = APIRouter(prefix="/api/admin/retention", tags=["admin"])


def default_retention_days() -> int:
    try:
        return max(30, int(os.environ.get("COMPLIANCE_AUDIT_RETENTION_DAYS", "365")))
    except ValueError:
        return 365


class RetentionStatus(BaseModel):
    retention_days: int
    total_activities: int
    older_than_window: int
    oldest_at: datetime | None = None


@router.get("", response_model=RetentionStatus)
def status(
    db: Session = Depends(get_session),
    _: User = Depends(require_admin),
) -> RetentionStatus:
    days = default_retention_days()
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    total = db.execute(select(func.count(Activity.id))).scalar_one()
    older = db.execute(
        select(func.count(Activity.id)).where(Activity.created_at < cutoff)
    ).scalar_one()
    oldest = db.execute(select(func.min(Activity.created_at))).scalar_one()
    return RetentionStatus(
        retention_days=days,
        total_activities=total,
        older_than_window=older,
        oldest_at=oldest,
    )


class PurgeResult(BaseModel):
    deleted: int
    retention_days: int


@router.post("/purge", response_model=PurgeResult)
def purge(
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> PurgeResult:
    days = default_retention_days()
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    result = db.execute(delete(Activity).where(Activity.created_at < cutoff))
    deleted = result.rowcount or 0

    # Log the purge itself so the audit log isn't empty after a wipe.
    db.add(
        Activity(
            actor_id=actor.id,
            action="audit.purged",
            target_type="activity",
            payload={"deleted": deleted, "retention_days": days},
        )
    )
    db.commit()
    return PurgeResult(deleted=deleted, retention_days=days)
