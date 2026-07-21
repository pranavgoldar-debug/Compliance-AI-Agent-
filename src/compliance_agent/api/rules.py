"""Rule CRUD endpoints (admin-managed)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
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


# ---------------------------------------------------------------------------
# AI page summary — fetch the rule's source_url, ask Claude to extract
# the form name, where to download the template, and key filing rules.
# Read-only, no DB writes. Used by the "Ask Claude about this page" button
# on the obligation drawer + the rules table.
# ---------------------------------------------------------------------------
class PageSummary(BaseModel):
    available: bool
    rule_id: int
    url: Optional[str] = None
    form_name: Optional[str] = None
    template_url: Optional[str] = None
    key_requirements: list[str] = []
    summary: Optional[str] = None
    error: Optional[str] = None


@router.post("/{rule_id}/read-source", response_model=PageSummary)
def read_source_with_claude(
    rule_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> PageSummary:
    """Have Claude read the rule's regulator page and surface the form
    template name, where to download it, and the key requirements.
    Compliance + finance both call this — anyone with a login can read
    the regulation summary."""
    from compliance_agent.ai import ai_available
    from compliance_agent.ai.llm_client import make_client
    from compliance_agent.ai.regulation_watcher import _fetch

    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")

    url = (rule.source_url or "").strip()
    if not url:
        return PageSummary(
            available=False,
            rule_id=rule_id,
            error="No source URL set for this rule. Admin can add one on Compliance Rules → click the source cell.",
        )

    if not ai_available():
        return PageSummary(
            available=False,
            rule_id=rule_id,
            url=url,
            error="AI is off. Set COMPLIANCE_AGENT_LIVE=1 + an API key on the server.",
        )

    status, text, err = _fetch(url)
    if err or not text:
        return PageSummary(
            available=False,
            rule_id=rule_id,
            url=url,
            error=err or "Empty page body — regulator may have blocked the fetch.",
        )

    text = text[:20000]  # cap input

    system = (
        "You read regulator portal pages and extract three things that a "
        "compliance team needs before filing:\n"
        "  1. form_name   — the official name/code of the form (e.g. "
        "     'GSTR-3B', 'Form 16A', 'STR via FINCAR'). null if not "
        "     explicit on the page.\n"
        "  2. template_url — an absolute URL on the same domain that links "
        "     directly to the form template / PDF / instructions. null if "
        "     not found.\n"
        "  3. key_requirements — 3-6 bullets of must-do items the filer "
        "     needs to remember (deadlines, attachments, fees, where to "
        "     submit). One sentence each, plain English.\n"
        "Also write a 2-sentence summary of what this filing is for.\n"
        "If the page is irrelevant or a generic homepage, set form_name and "
        "template_url to null and explain in summary."
    )

    tool = {
        "name": "record_summary",
        "description": "Record the extracted page summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "form_name": {"type": ["string", "null"]},
                "template_url": {"type": ["string", "null"]},
                "key_requirements": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "summary": {"type": "string"},
            },
            "required": ["summary", "key_requirements"],
        },
    }

    try:
        client = make_client()
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=1500,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": "record_summary"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Rule context: form_name={rule.form_name!r}, "
                        f"authority={rule.authority!r}, "
                        f"frequency={rule.frequency!r}.\n\n"
                        f"Page text from {url}:\n\n~~~\n{text}\n~~~"
                    ),
                }
            ],
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "record_summary":
                raw = block.input or {}
                return PageSummary(
                    available=True,
                    rule_id=rule_id,
                    url=url,
                    form_name=raw.get("form_name"),
                    template_url=raw.get("template_url"),
                    key_requirements=raw.get("key_requirements") or [],
                    summary=raw.get("summary"),
                )
    except Exception as e:  # noqa: BLE001
        return PageSummary(
            available=False, rule_id=rule_id, url=url, error=f"Claude call failed: {e}"
        )
    return PageSummary(
        available=False, rule_id=rule_id, url=url, error="No structured response from Claude."
    )
