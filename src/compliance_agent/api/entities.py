"""Entity CRUD endpoints."""
from __future__ import annotations

import re
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
    """Find applicable regulations (HYBRID): the deterministic condition engine
    decides each item's verdict (mandatory / conditional / not_applicable) from
    the entity's answers; the AI fills the one-line reason. Items without a
    machine condition fall back to the AI verdict."""
    from compliance_agent.db import RuleStatus
    from compliance_agent.api.licenses import _build_profile_block
    from compliance_agent.condition_engine import classify
    from compliance_agent.rule_extractor import assess_obligations, is_live

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
            "notes": "Nothing discovered yet — run Refresh Regulations first.",
        }

    attrs = _build_condition_attrs(entity)

    # AI is used ONLY for the reason text now (verdict comes from conditions).
    ai_by_form: dict[str, object] = {}
    ai_notes = None
    if is_live():
        profile_block = (
            (_build_profile_block(entity.finance_profile) or "\n\nCOMPANY PROFILE: (no primary answers)")
            + _secondary_answers_block(entity.qualification)
        )
        obligations_block = "\n".join(
            f"- {r.form_name} | {r.category} | {r.frequency}"
            + (f" | note: {r.applicability_note}" if r.applicability_note else "")
            for r in discovered
        )
        try:
            result = assess_obligations(
                profile_block, obligations_block,
                jurisdiction_hint=entity.jurisdiction_code,
            )
            ai_by_form = {v.form_name: v for v in result.verdicts}
            ai_notes = result.notes
        except Exception:  # noqa: BLE001 — reasons are best-effort; verdicts are deterministic
            ai_by_form = {}

    # The entity's answered VAT/GST cadence overrides the cadence a VAT return
    # was discovered with, so the return doesn't show e.g. 'Quarterly' after the
    # user answered 'monthly'. Persisted on the rule so the calendar matches too.
    vat_override = _vat_return_overrides(entity.finance_profile)

    items = []
    for r in discovered:
        aiv = ai_by_form.get(r.form_name)
        # Verdict is DETERMINISTIC so repeated runs with unchanged answers give
        # the same columns: the condition engine when the rule has a condition,
        # else the keyword activity-gate + the rule's own applicability flag. The
        # AI fills only the reason text below — never the verdict.
        verdict = (
            classify(r.condition, attrs) if r.condition else _fallback_verdict(r, entity)
        )
        reason = (
            (getattr(aiv, "reason", None) if aiv else None)
            or r.applicability_note
            or "Kept pending verification."
        )
        frequency, due = r.frequency, r.due_date_rule
        if vat_override and _is_vat_return(r):
            frequency, due = vat_override
            r.frequency, r.due_date_rule = frequency, due
        items.append(
            {
                "rule_id": r.id,
                "name": r.name,
                "form_name": r.form_name,
                "category": r.category,
                "function": r.responsible_function,
                "frequency": frequency,
                "verdict": verdict,
                "reason": reason,
                "triggering_factors": (getattr(aiv, "triggering_factors", None) if aiv else None)
                or r.triggering_activity,
                "due": due,
                "basis": r.source_url or r.authority,
                "source_url": r.source_url,
                "jurisdiction": r.jurisdiction_code,
            }
        )
    # Cache so the inventory survives reloads (re-runs on the button).
    entity.qualification = {**(entity.qualification or {}), "assessment": items}
    log_activity(
        db, actor_id=user.id, action="entity.assessed_obligations",
        target_type="entity", target_id=entity_id, payload={"count": len(items)},
    )
    db.commit()
    return {"available": True, "items": items, "notes": ai_notes}


def _build_condition_attrs(entity: Entity) -> dict:
    """Build the canonical attribute dict the condition engine evaluates against:
    primary flags (yes/no/tbc → true/false/absent) + mapped secondary params."""
    from compliance_agent.activity_gate import PRIMARY_ACTIVITY_FLAGS

    profile = entity.finance_profile or {}
    attrs: dict = {}
    for flag in PRIMARY_ACTIVITY_FLAGS:
        v = str(profile.get(flag, "")).strip().lower()
        if v == "yes":
            attrs[flag] = True
        elif v in ("no", "na"):
            attrs[flag] = False
        # tbc / missing → leave absent (unknown → safe-include)
    band = lambda key: str(profile.get(key, "")).strip().lower()  # noqa: E731
    if band("ct_income_band") in ("above", "below"):
        attrs["corporate_tax_threshold_met"] = band("ct_income_band") == "above"
    if band("tp_threshold") in ("above", "below"):
        attrs["group_consolidated_revenue_threshold_met"] = band("tp_threshold") == "above"
    if band("vat_frequency"):
        attrs["vat_return_frequency"] = band("vat_frequency")
    if band("esr_income") in ("yes", "no", "na"):
        attrs["esr_earns_income"] = band("esr_income") == "yes"
    # Fold in any qualification answers whose key already matches a canonical attr.
    for k, val in ((entity.qualification or {}).get("answers") or {}).items():
        if k in attrs:
            continue
        lv = str(val).strip().lower()
        attrs[k] = True if lv == "yes" else False if lv in ("no", "na") else val
    return attrs


def _fallback_verdict(rule, entity) -> str:
    """Deterministic verdict for a rule that carries no machine `condition`, so
    repeated 'Find applicable regulations' runs with the same answers are stable
    (the AI is used only for the reason text, never the verdict). The keyword
    activity-gate can rule it out; otherwise the rule's own Mandatory/Conditional
    flag decides."""
    from compliance_agent.activity_gate import entity_applicability, NOT_APPLICABLE
    from compliance_agent.db import Applicability

    if entity_applicability(
        entity.finance_profile,
        name=rule.name or "",
        form_name=rule.form_name or "",
        category=rule.category or "",
        area=rule.area or "",
    ) == NOT_APPLICABLE:
        return "not_applicable"
    return "mandatory" if rule.applicability == Applicability.mandatory else "conditional"


def _dedupe_key(text: Optional[str]) -> str:
    """Normalize a filing name/form for duplicate detection: lowercase, drop
    parenthetical asides, strip punctuation and collapse whitespace, and remove
    generic filler words so 'Annual Accounts' and 'Annual Accounts (filing)'
    or 'Annual Accounts Return' collapse to the same key."""
    s = re.sub(r"\([^)]*\)", " ", (text or "").lower())
    s = re.sub(r"[^a-z0-9]+", " ", s)
    # Drop noise words that don't distinguish one filing from another.
    drop = {"the", "a", "an", "of", "for", "to", "and", "filing", "form"}
    return " ".join(w for w in s.split() if w not in drop).strip()


def _vat_return_overrides(profile: Optional[dict]) -> Optional[tuple[str, str]]:
    """If the entity answered the VAT/GST return cadence, return the
    (frequency, due_date_rule) the VAT return should actually carry — so a return
    discovered as 'Quarterly' is corrected to the answered cadence instead of
    contradicting it. Returns None when the cadence wasn't answered."""
    freq = str((profile or {}).get("vat_frequency", "")).strip().lower()
    return {
        "monthly": (
            "Monthly",
            "Filed monthly — due the month after each month-end, per the tax "
            "authority's deadline.",
        ),
        "quarterly": (
            "Quarterly",
            "Filed quarterly — due the month after each quarter-end, per the tax "
            "authority's deadline.",
        ),
        "annual": (
            "Annual",
            "Filed annually — due after the VAT/GST year-end, per the tax "
            "authority's deadline.",
        ),
    }.get(freq)


def _is_vat_return(rule) -> bool:
    """True for a recurring VAT/GST *return* (not a one-off registration), so the
    answered cadence is applied to the right rule."""
    blob = (str(rule.name or "") + " " + str(rule.form_name or "")).lower()
    cat = str(rule.category or "").lower()
    is_vat = "vat" in blob or "gst" in blob or cat in ("vat", "gst/hst", "gst")
    return is_vat and "return" in blob


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


@router.get("/{entity_id}/gaps")
def entity_gaps(
    entity_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Gap-detection over the discovered list + Primary Activity answers:
      - empty_domains: a flag answered Yes but NO discovered item maps to it
        (that family likely wasn't researched — re-run discovery).
      - ungated_items: discovered items that map to no primary flag at all
        (the 'needs a new flag/question' class).
    (The spec's 'partial domain' check needs coverage_notes, which our
    discovery doesn't emit yet — omitted.)"""
    from compliance_agent.db import RuleStatus
    from compliance_agent.activity_gate import matched_activities, PRIMARY_ACTIVITY_FLAGS

    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found.")

    discovered = [
        r for r in entity.rules
        if r.status in (RuleStatus.staging, RuleStatus.production)
    ]
    profile = entity.finance_profile or {}

    flag_hits: dict[str, int] = {f: 0 for f in PRIMARY_ACTIVITY_FLAGS}
    ungated: list[dict] = []
    for r in discovered:
        hits = matched_activities(r.name or "", r.form_name or "", r.category or "", r.area or "")
        if not hits:
            ungated.append({"form_name": r.form_name or r.name, "category": r.category})
        for h in hits:
            flag_hits[h] = flag_hits.get(h, 0) + 1

    empty_domains = [
        flag
        for flag, ans in profile.items()
        if str(ans).strip().lower() == "yes"
        and flag in PRIMARY_ACTIVITY_FLAGS
        and flag_hits.get(flag, 0) == 0
    ]
    # Check #2 — domains the model only skimmed (coverage_notes != Confirmed).
    cov = (entity.qualification or {}).get("coverage_notes") or []
    partial_domains = [
        {"domain": c.get("domain"), "status": c.get("status"), "note": c.get("note")}
        for c in cov
        if "confirm" not in str(c.get("status", "")).lower()
    ]
    return {
        "empty_domains": empty_domains,
        "ungated_items": ungated[:50],
        "ungated_count": len(ungated),
        "partial_domains": partial_domains,
    }


@router.post("/{entity_id}/discover-regulations")
def discover_entity_regulations(
    entity_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    """Entity-level discovery: from the entity's Nature of Operations,
    jurisdiction and ALL its licenses, ask the AI for the MAXIMAL set of
    regulatory obligations (all functions / item types, assume every activity
    present). Works even with no license. Persists new items as Staging."""
    from compliance_agent.db import License, Rule, RuleStatus
    from compliance_agent.classification import derive_function
    from compliance_agent.rule_extractor import (
        extract_rules_from_text,
        is_live,
        RuleExtractorUnavailable,
    )
    from compliance_agent.api.licenses import _read_license_text, _MAX_PROMPT_CHARS

    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found.")
    if not is_live():
        return {"available": False, "created": 0, "notes": "AI is off — set COMPLIANCE_AGENT_LIVE=1 + an API key."}

    juris = entity.jurisdiction_code
    licenses = db.execute(select(License).where(License.entity_id == entity_id)).scalars().all()
    lic_lines = [
        f"- {l.name} | {l.authority} | type {l.license_type or 'n/a'} | no {l.license_number or 'n/a'}"
        for l in licenses
    ] or ["(no licenses uploaded)"]
    lic_texts: list[str] = []
    for l in licenses:
        try:
            t = _read_license_text(l)
        except Exception:  # noqa: BLE001
            t = ""
        if t and len(t.strip()) >= 200:
            lic_texts.append(f"\n--- LICENSE DOCUMENT: {l.name} ---\n{t[:8000]}")

    context = (
        "Discover the regulatory obligations that GENUINELY APPLY to the entity "
        "below, grounded in its ACTUAL nature of operations, the licenses it "
        "holds, its legal type and its jurisdiction. Do NOT assume activities "
        "the entity has not stated, and do NOT pad the list with obligations "
        "that only apply to other business models. Return only items a "
        "compliance officer for THIS entity would reasonably expect to file.\n"
        "Cover all four functions WHERE RELEVANT — Finance/Tax, Legal/Corporate, "
        "Compliance/AML, HR/Payroll — and the item types that actually apply: "
        "filings, returns, licenses, permits, registrations and ongoing "
        "reporting obligations. Always include the baseline statutory "
        "obligations that any company of this legal type in this jurisdiction "
        "must meet (e.g. annual accounts/return, corporate tax, payroll/social "
        "security if it employs staff). Add activity-specific obligations ONLY "
        "when the nature of operations or a license clearly triggers them. If an "
        "activity is genuinely uncertain, leave it out — it is surfaced later "
        "via the qualification questions, not guessed here. One entry per "
        "distinct item.\n\n"
        f"ENTITY: {entity.name}\n"
        f"Jurisdiction: {juris}\n"
        f"Legal type: {entity.legal_type or '(unknown)'}\n"
        f"Nature of operations: {entity.nature_of_operation or '(not provided)'}\n\n"
        f"LICENSES HELD:\n" + "\n".join(lic_lines) + "\n" + "".join(lic_texts)
    )[:_MAX_PROMPT_CHARS]

    try:
        result = extract_rules_from_text(context, jurisdiction_hint=juris)
    except RuleExtractorUnavailable as exc:
        return {"available": False, "created": 0, "notes": str(exc)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Claude call failed: {exc}") from exc

    # Dedupe on the normalized name AND form_name, so near-duplicates the model
    # phrases slightly differently (e.g. two 'Annual Accounts' with different
    # due wording, or 'Annual Accounts' vs 'Annual Accounts (filing)') collapse
    # to a single rule instead of both landing on the discovered list.
    existing: set[str] = set()
    for r in entity.rules:
        existing.update(k for k in (_dedupe_key(r.name), _dedupe_key(r.form_name)) if k)
    created: list = []
    for cand in result.rules:
        keys = {k for k in (_dedupe_key(cand.name), _dedupe_key(cand.form_name)) if k}
        if not keys or keys & existing:
            continue
        existing |= keys
        rule = Rule(
            name=cand.name,
            jurisdiction_code=(juris or "xx")[:16],
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
            responsible_function=(
                getattr(cand, "owner_team", None)
                if getattr(cand, "owner_team", None) in ("Finance", "Compliance", "Legal", "HR")
                else derive_function(cand.category, cand.area)
            ),
            condition=getattr(cand, "condition", None),
            triggering_activity=getattr(cand, "triggering_activity", None),
            anchor=getattr(cand, "anchor", None),
            confidence=getattr(cand, "confidence", None),
            # Discovered draft — NOT yet in Review & Assign until a human sends it.
            sent_to_review=False,
            status=RuleStatus.staging,
            created_by_id=user.id,
        )
        rule.entities = [entity]
        db.add(rule)
        created.append(rule)
    db.flush()
    # Discovered rules are drafts (sent_to_review=False): they do NOT get a
    # calendar obligation here. That happens only when a human sends them to
    # Review & Assign (PATCH sets sent_to_review=True → ensure_obligations).
    # Persist coverage notes on the entity for the gap-detection 'Partial' check.
    cov = [
        {"domain": c.domain, "status": c.status, "note": c.note}
        for c in getattr(result, "coverage_notes", []) or []
    ]
    if cov:
        entity.qualification = {**(entity.qualification or {}), "coverage_notes": cov}
    log_activity(
        db, actor_id=user.id, action="entity.discovered_regulations",
        target_type="entity", target_id=entity_id, payload={"created": len(created)},
    )
    db.commit()
    return {"available": True, "created": len(created), "notes": result.notes}


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
