"""Rule CRUD endpoints (admin-managed)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_agent.api._helpers import log_activity
from compliance_agent.api.schemas import RuleCreate, RuleOut, RuleUpdate
from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.db import Entity, Rule, RuleStatus, User, get_session


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
