"""Entity CRUD endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_agent.api._helpers import log_activity, serialize_entity
from compliance_agent.api.schemas import EntityCreate, EntityOut, EntityUpdate
from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.db import Entity, User, get_session


router = APIRouter(prefix="/api/entities", tags=["entities"])


@router.get("", response_model=list[EntityOut])
def list_entities(
    jurisdiction_code: Optional[str] = Query(None),
    include_archived: bool = Query(False),
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[EntityOut]:
    stmt = select(Entity)
    if jurisdiction_code:
        stmt = stmt.where(Entity.jurisdiction_code == jurisdiction_code)
    if not include_archived:
        stmt = stmt.where(Entity.archived_at.is_(None))
    stmt = stmt.order_by(Entity.name)
    return [serialize_entity(e, db) for e in db.execute(stmt).scalars().all()]


@router.get("/{entity_id}", response_model=EntityOut)
def get_entity(
    entity_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> EntityOut:
    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found.")
    return serialize_entity(entity, db)


@router.post("", response_model=EntityOut, status_code=201)
def create_entity(
    payload: EntityCreate,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> EntityOut:
    entity = Entity(**payload.model_dump())
    db.add(entity)
    db.flush()
    log_activity(
        db, actor_id=user.id, action="entity.created", target_type="entity", target_id=entity.id
    )
    db.commit()
    db.refresh(entity)
    return serialize_entity(entity, db)


@router.patch("/{entity_id}", response_model=EntityOut)
def update_entity(
    entity_id: int,
    payload: EntityUpdate,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> EntityOut:
    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entity, field, value)
    log_activity(
        db, actor_id=user.id, action="entity.updated", target_type="entity", target_id=entity.id
    )
    db.commit()
    db.refresh(entity)
    return serialize_entity(entity, db)


@router.post("/{entity_id}/archive", response_model=EntityOut)
def archive_entity(
    entity_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> EntityOut:
    from datetime import datetime, timezone

    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found.")
    entity.archived_at = datetime.now(tz=timezone.utc)
    log_activity(
        db, actor_id=user.id, action="entity.archived", target_type="entity", target_id=entity.id
    )
    db.commit()
    db.refresh(entity)
    return serialize_entity(entity, db)


@router.post("/archive-org-chart-extras")
def archive_org_chart_extras(
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> dict:
    """Admin-only: archive the entities the org-chart import added that aren't
    in the Excel/seed entity list (e.g. UAB Hokodo, the Australia/IFSC cos), so
    the workspace is back to the Excel's entity set. Only touches those extras."""
    from datetime import datetime, timezone

    from compliance_agent.data.org_chart import ORG_ENTITIES, _norm
    from compliance_agent.db.seed import DEMO_ENTITIES

    keep = {_norm(e["name"]) for e in DEMO_ENTITIES}
    extras = {_norm(e["name"]) for e in ORG_ENTITIES} - keep

    rows = (
        db.execute(select(Entity).where(Entity.archived_at.is_(None)))
        .scalars()
        .all()
    )
    archived: list[str] = []
    now = datetime.now(tz=timezone.utc)
    for e in rows:
        if _norm(e.name) in extras:
            e.archived_at = now
            archived.append(e.name)
    log_activity(
        db,
        actor_id=user.id,
        action="entities.archived_org_chart_extras",
        target_type="entity",
        target_id=None,
        payload={"archived": archived},
    )
    db.commit()
    return {"archived": len(archived), "names": archived}
