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
    fields = payload.model_dump(exclude_unset=True)
    for field, value in fields.items():
        setattr(entity, field, value)
    # When the Primary Activity answers change, reconcile this entity's calendar:
    # filings that are now not-applicable lose their pending obligations; ones
    # that are applicable (re)gain them. Keeps the calendar in lock-step with
    # the answers (deterministic gating — see activity_gate.py).
    if "finance_profile" in fields:
        from compliance_agent.activity_gate import NOT_APPLICABLE, entity_applicability
        from compliance_agent.api.rules import (
            _delete_pending_for_entity_rule,
            ensure_obligations_for_rule,
        )

        for rule in entity.rules:
            verdict = entity_applicability(
                entity.finance_profile, name=rule.name, form_name=rule.form_name,
                category=rule.category, area=rule.area,
            )
            if verdict == NOT_APPLICABLE:
                _delete_pending_for_entity_rule(db, rule.id, entity.id)
            else:
                ensure_obligations_for_rule(db, rule)
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


@router.post("/{entity_id}/assess-obligations")
def assess_entity_obligations(
    entity_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    """AI step: read the entity's Primary + Secondary Activity answers and the
    obligations discovered for it, and classify each as mandatory / conditional
    / not_applicable for THIS entity. Returns per-obligation verdicts."""
    from compliance_agent.db import Rule, RuleStatus
    from compliance_agent.api.licenses import _build_profile_block
    from compliance_agent.rule_extractor import (
        assess_obligations,
        is_live,
        RuleExtractorUnavailable,
    )

    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found.")

    discovered = [
        r
        for r in entity.rules
        if r.status in (RuleStatus.staging, RuleStatus.production)
    ]
    if not discovered:
        return {
            "available": True,
            "items": [],
            "notes": "Nothing discovered yet — run Find Regulations first.",
        }

    profile_block = (
        (_build_profile_block(entity.finance_profile) or "\n\nCOMPANY PROFILE: (no primary answers)")
        + _secondary_answers_block(entity.qualification)
    )
    obligations_block = "\n".join(
        f"- {r.form_name} | {r.category} | {r.frequency} | "
        f"currently {getattr(r.applicability, 'value', r.applicability)}"
        + (f" | note: {r.applicability_note}" if r.applicability_note else "")
        for r in discovered
    )

    if not is_live():
        return {
            "available": False,
            "items": [],
            "notes": "AI is off — set COMPLIANCE_AGENT_LIVE=1 plus an API key.",
        }

    try:
        result = assess_obligations(
            profile_block,
            obligations_block,
            jurisdiction_hint=entity.jurisdiction_code,
        )
    except RuleExtractorUnavailable as exc:
        return {"available": False, "items": [], "notes": str(exc)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Claude call failed: {exc}") from exc

    by_form = {r.form_name: r for r in discovered}
    items = []
    for v in result.verdicts:
        r = by_form.get(v.form_name)
        items.append(
            {
                "rule_id": r.id if r else None,
                "name": r.name if r else v.form_name,
                "form_name": v.form_name,
                "category": r.category if r else None,
                "frequency": r.frequency if r else None,
                "verdict": v.verdict,
                "reason": v.reason,
                "triggering_factors": v.triggering_factors,
                "frequency": r.frequency if r else None,
                "due": r.due_date_rule if r else None,
                "basis": (r.source_url or r.authority) if r else None,
                "jurisdiction": r.jurisdiction_code if r else entity.jurisdiction_code,
            }
        )
    # Cache the result on the entity so the inventory survives reloads without
    # re-running the AI (the Reassess button re-runs it on demand).
    entity.qualification = {**(entity.qualification or {}), "assessment": items}
    log_activity(
        db,
        actor_id=user.id,
        action="entity.assessed_obligations",
        target_type="entity",
        target_id=entity_id,
        payload={"count": len(items)},
    )
    db.commit()
    return {"available": True, "items": items, "notes": result.notes}


def _secondary_answers_block(qualification: Optional[dict]) -> str:
    """Render the entity's adaptive (secondary) question answers for the prompt."""
    if not qualification:
        return ""
    questions = qualification.get("questions") or []
    answers = qualification.get("answers") or {}
    lines: list[str] = []
    for q in questions:
        key = q.get("key")
        ans = answers.get(key)
        if not ans:
            continue
        label_for = {o.get("value"): o.get("label") for o in (q.get("options") or [])}
        lines.append(f"- {q.get('question')}: {label_for.get(ans, ans)}")
    if not lines:
        return ""
    return "\n\nADAPTIVE QUALIFICATION ANSWERS:\n" + "\n".join(lines)


@router.post("/{entity_id}/generate-questions")
def generate_entity_questions(
    entity_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    """Generate adaptive secondary qualification questions for this entity from
    its nature of operations, licenses, jurisdiction and discovered items.
    Merges into entity.qualification, preserving answers to questions that
    survive."""
    from compliance_agent.db import License, RuleStatus
    from compliance_agent.rule_extractor import (
        generate_secondary_questions,
        is_live,
        RuleExtractorUnavailable,
    )

    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found.")
    if not is_live():
        return {"available": False, "questions": [], "notes": "AI is off."}

    discovered = [
        r for r in entity.rules
        if r.status in (RuleStatus.staging, RuleStatus.production)
    ]
    licenses = db.execute(select(License).where(License.entity_id == entity_id)).scalars().all()
    lic_block = "\n".join(
        f"- {l.name} | {l.authority} | {l.license_type or 'n/a'} | {l.license_number or 'n/a'}"
        for l in licenses
    ) or "(none uploaded)"
    items_block = "\n".join(f"- {r.form_name} ({r.category})" for r in discovered) or "(none yet)"
    context = (
        f"ENTITY: {entity.name}\n"
        f"Jurisdiction: {entity.jurisdiction_code}\n"
        f"Legal type: {entity.legal_type or '(unknown)'}\n"
        f"Nature of operations: {entity.nature_of_operation or '(not provided)'}\n\n"
        f"LICENSES HELD:\n{lic_block}\n\n"
        f"REGULATORY ITEMS ALREADY DISCOVERED:\n{items_block}\n"
    )

    try:
        result = generate_secondary_questions(context, )
    except RuleExtractorUnavailable as exc:
        return {"available": False, "questions": [], "notes": str(exc)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Claude call failed: {exc}") from exc

    questions = [
        {
            "key": q.key,
            "question": q.question,
            "options": [{"value": o.value, "label": o.label} for o in q.options],
            "drives": q.drives,
            "primary_key": q.primary_key,
        }
        for q in result.questions
    ]
    prev_answers = (entity.qualification or {}).get("answers") or {}
    keys = {q["key"] for q in questions}
    merged_answers = {k: v for k, v in prev_answers.items() if k in keys}
    entity.qualification = {
        **(entity.qualification or {}),
        "questions": questions,
        "answers": merged_answers,
    }
    log_activity(
        db, actor_id=user.id, action="entity.generated_questions",
        target_type="entity", target_id=entity_id, payload={"count": len(questions)},
    )
    db.commit()
    return {"available": True, "questions": questions, "notes": result.notes}
