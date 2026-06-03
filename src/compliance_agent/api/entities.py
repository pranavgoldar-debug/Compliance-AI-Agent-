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
    """Admin-only: permanently delete the entities the org-chart import added
    that aren't in the Excel/seed entity list (e.g. UAB Hokodo, the
    Australia/IFSC cos), along with their licences, documents, obligations and
    rule links. Only touches those extras — the Excel entities are untouched."""
    from sqlalchemy import delete as sa_delete

    from compliance_agent import storage
    from compliance_agent.data.org_chart import ORG_ENTITIES, _norm
    from compliance_agent.db import (
        Comment,
        Document,
        License,
        Notification,
        Obligation,
    )
    from compliance_agent.db.seed import DEMO_ENTITIES

    keep = {_norm(e["name"]) for e in DEMO_ENTITIES}
    extras = {_norm(e["name"]) for e in ORG_ENTITIES} - keep

    rows = db.execute(select(Entity)).scalars().all()
    targets = [e for e in rows if _norm(e.name) in extras]
    removed: list[str] = []
    paths: list[str] = []

    for e in targets:
        # Obligations + their dependents (no DB cascade on obligation.entity_id).
        obs = (
            db.execute(select(Obligation).where(Obligation.entity_id == e.id))
            .scalars()
            .all()
        )
        for ob in obs:
            db.execute(sa_delete(Comment).where(Comment.obligation_id == ob.id))
            db.execute(
                sa_delete(Notification).where(Notification.obligation_id == ob.id)
            )
            db.execute(sa_delete(Document).where(Document.obligation_id == ob.id))
            db.delete(ob)
        # Licences + documents (capture storage paths for cleanup).
        for lic in (
            db.execute(select(License).where(License.entity_id == e.id))
            .scalars()
            .all()
        ):
            if lic.storage_path:
                paths.append(lic.storage_path)
            db.delete(lic)
        for doc in (
            db.execute(select(Document).where(Document.entity_id == e.id))
            .scalars()
            .all()
        ):
            if doc.storage_path:
                paths.append(doc.storage_path)
            db.delete(doc)
        # Rule links (m2m) then the entity itself.
        e.rules = []
        db.flush()
        removed.append(e.name)
        db.delete(e)

    log_activity(
        db,
        actor_id=user.id,
        action="entities.deleted_org_chart_extras",
        target_type="entity",
        target_id=None,
        payload={"removed": removed},
    )
    db.commit()
    for p in paths:
        try:
            storage.delete(p)
        except Exception:  # noqa: BLE001
            pass
    return {"archived": len(removed), "names": removed}


def _hard_delete_entity(db: Session, e: Entity) -> list[str]:
    """Delete an entity + everything that hangs off it (licences, documents,
    obligations and their comments/notifications, rule links). Returns the
    storage paths to sweep. Does NOT commit."""
    from sqlalchemy import delete as sa_delete

    from compliance_agent.db import (
        Comment,
        Document,
        License,
        Notification,
        Obligation,
    )

    paths: list[str] = []
    obs = (
        db.execute(select(Obligation).where(Obligation.entity_id == e.id))
        .scalars()
        .all()
    )
    for ob in obs:
        db.execute(sa_delete(Comment).where(Comment.obligation_id == ob.id))
        db.execute(sa_delete(Notification).where(Notification.obligation_id == ob.id))
        db.execute(sa_delete(Document).where(Document.obligation_id == ob.id))
        db.delete(ob)
    for lic in (
        db.execute(select(License).where(License.entity_id == e.id)).scalars().all()
    ):
        if lic.storage_path:
            paths.append(lic.storage_path)
        db.delete(lic)
    for doc in (
        db.execute(select(Document).where(Document.entity_id == e.id)).scalars().all()
    ):
        if doc.storage_path:
            paths.append(doc.storage_path)
        db.delete(doc)
    e.rules = []
    db.flush()
    db.delete(e)
    return paths


@router.delete("/{entity_id}", status_code=204)
def delete_entity(
    entity_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    """Admin-only: permanently delete one entity and everything tied to it."""
    from compliance_agent import storage
    from fastapi import Response

    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found.")
    name = entity.name
    paths = _hard_delete_entity(db, entity)
    log_activity(
        db,
        actor_id=user.id,
        action="entity.deleted",
        target_type="entity",
        target_id=entity_id,
        payload={"name": name},
    )
    db.commit()
    for p in paths:
        try:
            storage.delete(p)
        except Exception:  # noqa: BLE001
            pass
    return Response(status_code=204)
