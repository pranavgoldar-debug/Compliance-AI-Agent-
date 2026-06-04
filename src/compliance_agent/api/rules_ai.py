"""AI-backed rule extraction endpoint.

Admin pastes raw regulatory text -> Claude extracts candidate Rule rows ->
admin reviews + ticks -> bulk-create endpoint persists them as Staging
rules associated with selected entities.

Only the extraction call hits Claude. Creation is plain SQL.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from compliance_agent.api._helpers import log_activity
from compliance_agent.classification import derive_function
from compliance_agent.api.rules import _serialize_rule
from compliance_agent.api.schemas import RuleOut
from compliance_agent.auth import require_admin
from compliance_agent.db import (
    Applicability,
    Entity,
    Rule,
    RuleStatus,
    User,
    get_session,
)
from compliance_agent.rule_extractor import (
    CandidateRule,
    RuleExtractionResult,
    RuleExtractorUnavailable,
    extract_rules_from_text,
    is_live,
)


router = APIRouter(prefix="/api/rules", tags=["rules-ai"])


class ExtractRequest(BaseModel):
    text: str
    jurisdiction_hint: Optional[str] = None


class ExtractResponse(BaseModel):
    available: bool
    jurisdiction_hint: Optional[str] = None
    rules: list[CandidateRule]
    notes: Optional[str] = None


@router.post("/extract", response_model=ExtractResponse)
def extract_rules(
    payload: ExtractRequest,
    user: User = Depends(require_admin),
) -> ExtractResponse:
    if not is_live():
        # Don't 500 — surface a structured "off" response so the UI can show a
        # friendly banner instead of a generic error.
        return ExtractResponse(
            available=False,
            jurisdiction_hint=payload.jurisdiction_hint,
            rules=[],
            notes=(
                "AI rule extraction is off. Set COMPLIANCE_AGENT_LIVE=1 and "
                "ANTHROPIC_API_KEY (or OPENROUTER_API_KEY) in your server environment, then retry."
            ),
        )

    if len(payload.text.strip()) < 80:
        raise HTTPException(
            status_code=400,
            detail="Paste at least 80 characters of regulatory text to extract from.",
        )

    try:
        result: RuleExtractionResult = extract_rules_from_text(
            payload.text,
            jurisdiction_hint=payload.jurisdiction_hint,
        )
    except RuleExtractorUnavailable as exc:
        return ExtractResponse(
            available=False,
            jurisdiction_hint=payload.jurisdiction_hint,
            rules=[],
            notes=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        # Surface Anthropic / network errors verbatim — admin needs to see them
        # to know whether to retry, top up credits, fix the key, etc.
        raise HTTPException(status_code=502, detail=f"Claude call failed: {exc}") from exc

    return ExtractResponse(
        available=True,
        jurisdiction_hint=result.jurisdiction_hint or payload.jurisdiction_hint,
        rules=result.rules,
        notes=result.notes,
    )


class BulkCreatePayload(BaseModel):
    jurisdiction_code: str
    rules: list[CandidateRule]
    entity_ids: list[int] = []
    status: RuleStatus = RuleStatus.staging


class BulkCreateResponse(BaseModel):
    created: list[RuleOut]


@router.post("/bulk-create", response_model=BulkCreateResponse)
def bulk_create_rules(
    payload: BulkCreatePayload,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> BulkCreateResponse:
    if not payload.rules:
        raise HTTPException(status_code=400, detail="Provide at least one rule to create.")

    # Keep the jurisdiction code within the column width (a free-text AI hint
    # like "United Arab Emirates" would otherwise blow up the insert with a
    # 500). Normalise to lowercase + clamp to 16 chars.
    juris_code = (payload.jurisdiction_code or "").strip().lower()[:16] or "xx"

    entities = []
    if payload.entity_ids:
        from sqlalchemy import select

        entities = (
            db.execute(select(Entity).where(Entity.id.in_(payload.entity_ids)))
            .scalars()
            .all()
        )

    created: list[Rule] = []
    for cand in payload.rules:
        rule = Rule(
            name=cand.name,
            jurisdiction_code=juris_code,
            category=cand.category,
            area=cand.area,
            form_name=cand.form_name,
            authority=cand.authority,
            frequency=cand.frequency,
            due_date_rule=cand.due_date_rule,
            payment_rule=cand.payment_rule,
            applicability=cand.applicability,
            applicability_note=cand.applicability_note,
            tax_type=cand.tax_type,
            plain_description=cand.plain_description,
            responsible_function=derive_function(cand.category, cand.area),
            status=payload.status,
            created_by_id=user.id,
        )
        rule.entities = list(entities)
        db.add(rule)
        created.append(rule)
    db.flush()

    # As soon as obligations enter review (staging), put them on the calendar.
    from compliance_agent.api.rules import ensure_obligations_for_rule

    for rule in created:
        ensure_obligations_for_rule(db, rule)

    log_activity(
        db,
        actor_id=user.id,
        action="rule.bulk_created",
        target_type="rule",
        payload={
            "count": len(created),
            "jurisdiction": payload.jurisdiction_code,
            "entity_ids": payload.entity_ids,
            "source": "ai_extraction",
        },
    )
    db.commit()
    for rule in created:
        db.refresh(rule)
    return BulkCreateResponse(created=[_serialize_rule(r) for r in created])
