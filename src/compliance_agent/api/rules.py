"""Rule CRUD endpoints (admin-managed)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_agent.api._helpers import log_activity, serialize_user
from compliance_agent.api.schemas import RuleCreate, RuleOut, RuleSnapshotOut, RuleUpdate
from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.db import (
    Entity,
    Rule,
    RuleSnapshot,
    RuleStatus,
    User,
    get_session,
)


router = APIRouter(prefix="/api/rules", tags=["rules"])


def _serialize_rule(rule: Rule) -> RuleOut:
    return RuleOut(
        id=rule.id,
        name=rule.name,
        jurisdiction_code=rule.jurisdiction_code,
        category=rule.category,
        area=rule.area,
        form_name=rule.form_name,
        authority=rule.authority,
        frequency=rule.frequency,
        due_date_rule=rule.due_date_rule,
        payment_rule=rule.payment_rule,
        applicability=rule.applicability,
        applicability_note=rule.applicability_note,
        status=rule.status,
        source_url=rule.source_url,
        submission_url=rule.submission_url,
        source_text=rule.source_text,
        source_changed_at=rule.source_changed_at,
        entity_ids=[e.id for e in rule.entities],
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("", response_model=list[RuleOut])
def list_rules(
    jurisdiction_code: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[RuleStatus] = Query(None),
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[RuleOut]:
    stmt = select(Rule)
    if jurisdiction_code:
        stmt = stmt.where(Rule.jurisdiction_code == jurisdiction_code)
    if category:
        stmt = stmt.where(Rule.category == category)
    if status:
        stmt = stmt.where(Rule.status == status)
    stmt = stmt.order_by(Rule.jurisdiction_code, Rule.category, Rule.name)
    return [_serialize_rule(r) for r in db.execute(stmt).scalars().all()]


@router.get("/{rule_id}", response_model=RuleOut)
def get_rule(
    rule_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> RuleOut:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")
    return _serialize_rule(rule)


def _attach_entities(rule: Rule, entity_ids: list[int], db: Session) -> None:
    if not entity_ids:
        rule.entities = []
        return
    entities = db.execute(select(Entity).where(Entity.id.in_(entity_ids))).scalars().all()
    rule.entities = list(entities)


@router.post("", response_model=RuleOut, status_code=201)
def create_rule(
    payload: RuleCreate,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> RuleOut:
    data = payload.model_dump()
    entity_ids = data.pop("entity_ids", [])
    rule = Rule(**data, created_by_id=user.id)
    db.add(rule)
    db.flush()
    _attach_entities(rule, entity_ids, db)
    log_activity(
        db, actor_id=user.id, action="rule.created", target_type="rule", target_id=rule.id
    )
    db.commit()
    db.refresh(rule)
    return _serialize_rule(rule)


@router.patch("/{rule_id}", response_model=RuleOut)
def update_rule(
    rule_id: int,
    payload: RuleUpdate,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> RuleOut:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")
    data = payload.model_dump(exclude_unset=True)
    entity_ids = data.pop("entity_ids", None)
    for field, value in data.items():
        setattr(rule, field, value)
    if entity_ids is not None:
        _attach_entities(rule, entity_ids, db)
    log_activity(
        db, actor_id=user.id, action="rule.updated", target_type="rule", target_id=rule.id
    )
    db.commit()
    db.refresh(rule)
    return _serialize_rule(rule)


# ---------------------------------------------------------------------------
# Snapshots (Phase 7) — history of regulation-change checks
# ---------------------------------------------------------------------------
from sqlalchemy.orm import joinedload as _joinedload


@router.get("/{rule_id}/snapshots", response_model=list[RuleSnapshotOut])
def list_rule_snapshots(
    rule_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[RuleSnapshotOut]:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")
    rows = db.execute(
        select(RuleSnapshot)
        .where(RuleSnapshot.rule_id == rule_id)
        .options(_joinedload(RuleSnapshot.fetched_by))
        .order_by(RuleSnapshot.fetched_at.desc())
        .limit(50)
    ).scalars().unique().all()
    return [
        RuleSnapshotOut(
            id=s.id,
            rule_id=s.rule_id,
            fetched_at=s.fetched_at,
            fetched_by=serialize_user(s.fetched_by),
            http_status=s.http_status,
            content_length=s.content_length,
            content_hash=s.content_hash,
            content_excerpt=s.content_excerpt,
            change_summary=s.change_summary,
        )
        for s in rows
    ]
