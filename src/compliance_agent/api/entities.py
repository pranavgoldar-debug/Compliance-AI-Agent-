"""Entity CRUD endpoints."""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

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
    from compliance_agent.api.licenses import canonical_fye

    data = payload.model_dump()
    # Normalise fiscal year-end to a short canonical 'DD-Mon' so any input
    # ('December', '31 December', '31/12') saves consistently and never
    # overflows the column (the cause of the HTTP 500).
    if data.get("fiscal_year_end"):
        data["fiscal_year_end"] = canonical_fye(data["fiscal_year_end"]) or str(
            data["fiscal_year_end"]
        )[:10]
    entity = Entity(**data)
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
    # Normalise fiscal year-end (case/format-insensitive, short canonical form)
    # so it saves consistently and never overflows the column.
    if fields.get("fiscal_year_end"):
        from compliance_agent.api.licenses import canonical_fye

        fields["fiscal_year_end"] = canonical_fye(fields["fiscal_year_end"]) or str(
            fields["fiscal_year_end"]
        )[:10]
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
    # Soft archive: flag the entity. Its obligations are NOT deleted — they are
    # hidden from the active calendar / obligations / tasks / dashboard views
    # (those filter out archived entities), so archiving an entity effectively
    # archives its obligations too, reversibly. A hard delete is what removes
    # the obligations for good.
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
    """Delete an entity + everything that hangs off it: licences, documents,
    obligations (and their comments/notifications + shared-calendar events),
    AND its rules — every rule left with no other entity after this one is
    removed is deleted too (For Action / Approved / Archived alike), so an
    entity's regulations don't linger in Review & Assign. Rules still shared
    with another entity are only unlinked. Returns storage paths to sweep.
    Does NOT commit."""
    from sqlalchemy import delete as sa_delete

    from compliance_agent import calendar_service
    from compliance_agent.api.rules import _delete_rule_cascade
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
    # Pull their shared Google Calendar events before the rows go.
    calendar_service.forget_obligations(db, [ob.id for ob in obs])
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
    # Rules: unlink this entity, then delete any rule now left with no entity
    # (i.e. it only belonged to this one) — incl. approved, discovered and
    # archived. Rules still attached to another entity are kept.
    rules = list(e.rules)
    e.rules = []
    db.flush()
    for r in rules:
        db.refresh(r)
        if not r.entities:
            _delete_rule_cascade(db, r)
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
    the entity's answers; the AI fills only the one-line reason. Items without a
    machine condition use the deterministic activity-gate fallback."""
    from datetime import date
    from compliance_agent.db import RuleStatus
    from compliance_agent.api.licenses import (
        _build_profile_block,
        _next_due_for_rule,
        _parse_fy_end,
    )
    from compliance_agent.condition_engine import classify
    from compliance_agent.rule_extractor import assess_obligations, is_live
    from compliance_agent.data.authority_urls import lookup as authority_url_lookup

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
    fy_end = _parse_fy_end(entity.fiscal_year_end)

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
        # Concrete next deadline — the same calculation the calendar uses — so
        # the inventory shows the actual date, not just the textual rule.
        try:
            next_due = _next_due_for_rule(r, date.today(), fy_end).isoformat()
        except Exception:  # noqa: BLE001 — best-effort; fall back to the text rule
            next_due = None
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
                "next_due": next_due,
                "basis": r.source_url or r.authority,
                # Verification link: the rule's own URL, else the official
                # authority website from the curated map.
                "source_url": r.source_url or authority_url_lookup(r.authority),
                "jurisdiction": r.jurisdiction_code,
            }
        )
    # Cache so the inventory survives reloads (re-runs on the button).
    entity.qualification = {**(entity.qualification or {}), "assessment": items}
    log_activity(
        db, actor_id=user.id, action="entity.assessed_obligations",
        target_type="entity", target_id=entity_id, payload={"count": len(items)},
    )
    # Persist so the inventory survives navigation / reload and only recomputes
    # when the user explicitly re-runs "Find applicable regulations".
    entity.last_assessment = {"items": items, "notes": ai_notes}
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
    (the AI is used only for the reason text, never the verdict).

    Decided from the filing's triggering activity answers:
      - a matched activity answered No/NA (and none Yes) -> not_applicable
      - a matched activity answered Yes (the trigger is confirmed) -> mandatory
      - matched but every answer is TBC/unanswered -> conditional (kept, unsure)
      - the filing maps to no activity -> conditional (no evidence it applies to
        THIS entity, so flag "verify" rather than assert Mandatory)
    """
    from compliance_agent.activity_gate import matched_activities

    profile = entity.finance_profile or {}
    hits = matched_activities(
        rule.name or "", rule.form_name or "", rule.category or "", rule.area or ""
    )
    if hits:
        answers = {str(profile.get(a, "")).strip().lower() for a in hits}
        if "yes" in answers:
            return "mandatory"
        if answers & {"no", "na"}:
            return "not_applicable"
        return "conditional"
    # No machine condition AND no matching activity -> we have no positive
    # evidence this filing applies to THIS entity. Flag it Conditional (verify),
    # never assert Mandatory — that's what produced a wall of false "mandatory".
    return "conditional"


def _dedupe_key(text: Optional[str]) -> str:
    """Normalize a filing name/form for duplicate detection so near-duplicates
    collapse to one key: lowercase, drop parenthetical asides, strip
    punctuation, remove generic filler words, SINGULARISE tokens (so
    'Asset'/'Assets' and 'Event'/'Events' match) and SORT them (so word-order
    variants like 'Notification of Significant Events' and 'Significant Events
    Notification' match). E.g. 'Client Money and Asset Return' and 'Client Money
    and Assets Return' collapse to the same key."""
    from compliance_agent.rule_normalize import normalize_phrase

    s = normalize_phrase(text)
    # Drop noise words that don't distinguish one filing from another.
    drop = {"the", "a", "an", "of", "for", "to", "and", "filing", "form"}
    toks = []
    for w in s.split():
        if w in drop:
            continue
        # Crude singularisation so plural/singular phrasings share a key. Only
        # for longer tokens, so short words aren't mangled. Applied to both
        # sides of the comparison, so it stays internally consistent.
        if len(w) >= 4 and w.endswith("s"):
            w = w[:-1]
        toks.append(w)
    # Sort so word order doesn't create a false distinction; dedupe tokens so an
    # acronym expansion that repeats words already present (e.g. "Full Payment
    # Submission (FPS)" → full/payment/submission twice) still yields one key.
    return " ".join(sorted(set(toks))).strip()


def _name_tokens_ordered(text: Optional[str]) -> list[str]:
    """The same normalized significant tokens as _dedupe_key but IN ORIGINAL
    ORDER (not sorted) — used to test acronym ↔ expansion matches."""
    from compliance_agent.rule_normalize import normalize_phrase

    s = normalize_phrase(text)
    drop = {"the", "a", "an", "of", "for", "to", "and", "filing", "form"}
    toks: list[str] = []
    for w in s.split():
        if w in drop:
            continue
        if len(w) >= 4 and w.endswith("s"):
            w = w[:-1]
        toks.append(w)
    return toks


def _acronym_dupe(a, b) -> bool:
    """True when two filings are the same one written as ACRONYM vs EXPANSION
    (e.g. '… FPS' vs '… Full Payment Submission', 'VAT return' vs 'Value Added
    Tax return'). Jurisdiction-agnostic: they must share context tokens, and one
    side's single extra token must be an acronym spelled by the other side's
    extra words (in order). The caller restricts to same authority + cadence."""
    aw = _name_tokens_ordered(a.name) or _name_tokens_ordered(a.form_name)
    bw = _name_tokens_ordered(b.name) or _name_tokens_ordered(b.form_name)
    common = set(aw) & set(bw)
    if not common:
        return False
    exa, exb = set(aw) - common, set(bw) - common

    def spells(single: set, words: list, multi: set) -> bool:
        if len(single) != 1 or len(multi) < 2:
            return False
        acro = next(iter(single))
        if not (2 <= len(acro) <= 6 and acro.isalpha()):
            return False
        seq = [w for w in words if w in multi]
        return "".join(w[0] for w in seq) == acro

    return spells(exa, bw, exb) or spells(exb, aw, exa)


def _norm_freq(freq: Optional[str]) -> str:
    """Normalize a frequency for duplicate signatures, so two rules count as the
    same filing only when their cadence also matches — this keeps genuinely
    distinct same-name filings (e.g. a Quarterly vs an Annual return) apart."""
    return re.sub(r"[^a-z0-9]+", "", (freq or "").lower())


def _dup_signatures(name, form_name, frequency, jurisdiction=None) -> set:
    """Duplicate signatures for a filing: the normalized name key and form key,
    each paired with the normalized cadence — plus a canonical form-code key
    (e.g. CANADA::T1134) when the filing maps to a known/leading form code. Two
    filings are duplicates when they share a signature, so the same filing under
    different phrasings ('T1134 return' / 'Foreign Affiliate Information Return')
    collapses via the shared canonical key, while genuinely different forms (T4
    vs T4A) never do."""
    from compliance_agent.rule_normalize import canonical_code

    f = _norm_freq(frequency)
    sigs = {(k, f) for k in (_dedupe_key(name), _dedupe_key(form_name)) if k}
    code = canonical_code(name, form_name, jurisdiction)
    if code:
        sigs.add((("canon", code), f))
    return sigs


def _entity_rules_fresh(db, entity) -> list:
    """Query the entity's rules straight from the DB (not the cached relationship
    collection), so dedupe sees rows added earlier in the SAME request after a
    flush — otherwise newly-created duplicates are invisible to the collapse."""
    from compliance_agent.db import Rule

    return (
        db.execute(select(Rule).where(Rule.entities.any(Entity.id == entity.id)))
        .scalars()
        .all()
    )


def _remove_rule_from_entity(db, rule, entity) -> None:
    """Remove a duplicate rule from THIS entity's view. If the rule is shared with
    other entities, just unlink it from this one (and drop this entity's
    obligations for it). If it belongs only to this entity, delete it outright.
    Works regardless of obligations or sharing, so the dedupe always takes
    effect."""
    from sqlalchemy import delete as sa_delete
    from compliance_agent.db import Obligation
    from compliance_agent.api.rules import _delete_rule_cascade

    others = [e for e in rule.entities if e.id != entity.id]
    if others:
        rule.entities = others
        db.execute(
            sa_delete(Obligation).where(
                Obligation.rule_id == rule.id, Obligation.entity_id == entity.id
            )
        )
        db.flush()
    else:
        _delete_rule_cascade(db, rule)


def _collapse_duplicate_rules(db, entity) -> int:
    """Remove duplicate rules for this entity. Group its rules (read FRESH from
    the DB) by duplicate signature (normalized name/form + cadence); within each
    group keep the safest copy — one that already has obligations, else the
    most-progressed (production > sent-to-review > staging), else the oldest — and
    remove the rest from this entity (unlink if shared, delete if not). Returns
    the number removed."""
    from collections import defaultdict
    from compliance_agent.db import RuleStatus
    from compliance_agent.rule_normalize import canonical_code

    groups: dict = defaultdict(list)
    for r in _entity_rules_fresh(db, entity):
        # Prefer the canonical form-code key so phrasing variants of the same
        # coded filing (T1134 x2, T4 x3) group together; fall back to the
        # normalized name key for uncoded filings.
        code = canonical_code(r.name, r.form_name, r.jurisdiction_code)
        if code:
            key = ("canon", code)
        else:
            key = _dedupe_key(r.name) or _dedupe_key(r.form_name)
        if key:
            groups[(key, _norm_freq(r.frequency))].append(r)

    removed = 0
    for rules in groups.values():
        if len(rules) < 2:
            continue
        keep, *rest = sorted(
            rules,
            key=lambda r: (
                1 if r.obligations else 0,
                1 if r.status == RuleStatus.production else 0,
                1 if getattr(r, "sent_to_review", False) else 0,
                -(r.id or 0),
            ),
            reverse=True,
        )
        for r in rest:
            _remove_rule_from_entity(db, r, entity)
            removed += 1

    # Pass 2 — full-form vs short-form: within the SAME authority + cadence,
    # collapse rules whose significant-token set is a subset of another's (e.g.
    # 'FCA periodic fee' vs 'FCA periodic fee and fee-tariff return', or 'PAYE
    # ... FPS' phrasings). The authority + frequency guard and a 2-token minimum
    # keep genuinely different filings apart. Re-read fresh so pass-1 removals
    # are reflected.
    db.flush()

    def _toks(r) -> frozenset:
        return frozenset((_dedupe_key(r.name) or _dedupe_key(r.form_name)).split())

    buckets: dict = defaultdict(list)
    for r in _entity_rules_fresh(db, entity):
        t = _toks(r)
        if len(t) >= 2:  # too-short names are unsafe to subset-match
            buckets[(_dedupe_key(r.authority), _norm_freq(r.frequency))].append((r, t))

    for items in buckets.values():
        if len(items) < 2:
            continue
        items.sort(key=lambda it: len(it[1]), reverse=True)  # longest = cluster seed
        used = [False] * len(items)
        for i in range(len(items)):
            if used[i]:
                continue
            cluster = [items[i][0]]
            used[i] = True
            for j in range(i + 1, len(items)):
                if not used[j] and (
                    items[j][1] <= items[i][1]
                    or items[i][1] <= items[j][1]
                    or _acronym_dupe(items[i][0], items[j][0])
                ):
                    cluster.append(items[j][0])
                    used[j] = True
            if len(cluster) < 2:
                continue
            keep, *rest = sorted(
                cluster,
                key=lambda r: (
                    1 if r.obligations else 0,
                    1 if r.status == RuleStatus.production else 0,
                    1 if getattr(r, "sent_to_review", False) else 0,
                    -(r.id or 0),
                ),
                reverse=True,
            )
            for r in rest:
                _remove_rule_from_entity(db, r, entity)
                removed += 1
    return removed


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


def _collapse_vat_returns(db, entity) -> int:
    """A VAT/GST return is filed at ONE cadence, so the model emitting both a
    Monthly and a Quarterly variant is a duplicate (unlike a genuine
    quarterly-vs-annual pair of *different* filings, which we keep apart). Keep a
    single VAT/GST return and stamp its cadence from the entity's answered
    vat_frequency (via _vat_return_overrides) — so it shows Monthly if they file
    monthly, Quarterly if quarterly. Removes the redundant obligation-free
    copies. Returns the number removed."""
    from compliance_agent.db import RuleStatus

    vat_rules = [r for r in _entity_rules_fresh(db, entity) if _is_vat_return(r)]
    if not vat_rules:
        return 0
    keep, *rest = sorted(
        vat_rules,
        key=lambda r: (
            1 if r.obligations else 0,
            1 if r.status == RuleStatus.production else 0,
            1 if getattr(r, "sent_to_review", False) else 0,
            -(r.id or 0),
        ),
        reverse=True,
    )
    # Stamp the kept return with the entity's answered cadence, if they gave one.
    override = _vat_return_overrides(entity.finance_profile)
    if override:
        keep.frequency, keep.due_date_rule = override
    removed = 0
    for r in rest:
        _remove_rule_from_entity(db, r, entity)
        removed += 1
    return removed


def _run_ai_dedupe(db, entity, rules, removable, *, min_count: int = 3) -> int:
    """Core AI de-dup for ONE entity: ask the model to cluster the genuine
    duplicates among `rules` (the deterministic signatures miss synonymous names,
    different authority spellings and generic-vs-specific phrasings), then remove
    the redundant copies — keeping the SAFEST in each cluster. `removable(rule)`
    decides which non-keepers may actually be deleted (discovery uses pure drafts
    only; the manual cleanup also collapses already-reviewed rows). Best-effort:
    any AI failure removes nothing."""
    from compliance_agent.db import RuleStatus
    from compliance_agent.rule_extractor import dedupe_filings, is_live

    if not is_live():
        return 0
    rules = sorted(rules, key=lambda r: r.id or 0)
    if len(rules) < min_count:
        return 0
    lines = [
        f"{i}. {(r.name or r.form_name or '(unnamed)')} | {r.authority or 'n/a'} "
        f"| {r.category or 'n/a'} | {r.frequency or 'n/a'}"
        for i, r in enumerate(rules, start=1)
    ]
    try:
        res = dedupe_filings("\n".join(lines))
    except Exception:  # noqa: BLE001 — dedupe is best-effort; never break the caller
        return 0

    def _safety(r):
        return (
            1 if r.obligations else 0,
            1 if r.status == RuleStatus.production else 0,
            1 if getattr(r, "sent_to_review", False) else 0,
            -(r.id or 0),
        )

    n = len(rules)
    seen: set = set()
    removed = 0
    for cl in res.clusters or []:
        idxs = [cl.keep_index, *(cl.drop_indices or [])]
        idxs = [x for x in idxs if isinstance(x, int) and 1 <= x <= n and x not in seen]
        if len(idxs) < 2:
            continue
        seen.update(idxs)
        members = [rules[x - 1] for x in idxs]
        keep = max(members, key=_safety)  # never auto-remove the safest copy
        for r in members:
            if r is not keep and removable(r):
                _remove_rule_from_entity(db, r, entity)
                removed += 1
    # Parent/child: drop the GENERIC parent obligations the model flagged as
    # redundant because the SPECIFIC children are already in the list.
    for x in getattr(res, "redundant_parents", None) or []:
        if not (isinstance(x, int) and 1 <= x <= n) or x in seen:
            continue
        seen.add(x)
        parent = rules[x - 1]
        if removable(parent):
            _remove_rule_from_entity(db, parent, entity)
            removed += 1
    if removed:
        db.flush()
    return removed


def _ai_collapse_duplicates(db, entity) -> int:
    """Discovery-time dedup. Only ever removes a PURE discovered draft (staging,
    not yet sent to review, no obligations), so a confirmed / calendar-scheduled /
    in-review filing is never deleted by a model mistake on a background refresh."""
    from compliance_agent.db import RuleStatus

    def _removable(r) -> bool:
        return (
            r.status == RuleStatus.staging
            and not getattr(r, "sent_to_review", False)
            and not r.obligations
        )

    return _run_ai_dedupe(db, entity, _entity_rules_fresh(db, entity), _removable)


def _reconcile_drafts(db, entity, keep_sigs: set) -> int:
    """Drop unreviewed AI drafts that the current (deterministic) discovery run no
    longer produces, so the discovered list reflects the LATEST run instead of
    accumulating across refreshes. Only obligation-free staging drafts not yet
    sent to Review & Assign are removed; confirmed / reviewed rules are kept, and
    VAT/GST returns are left to _collapse_vat_returns."""
    from compliance_agent.db import RuleStatus

    removed = 0
    for r in _entity_rules_fresh(db, entity):
        if _is_vat_return(r):
            continue
        if (
            r.status == RuleStatus.staging
            and not getattr(r, "sent_to_review", False)
            and not r.obligations
            and not (_dup_signatures(r.name, r.form_name, r.frequency, r.jurisdiction_code) & keep_sigs)
        ):
            _remove_rule_from_entity(db, r, entity)
            removed += 1
    return removed


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


# Human phrasing for the primary activity flags, used to feed CONFIRMED
# activities into discovery. POSITIVE-ONLY: only "yes" answers are fed, and only
# to EXPAND the universe — a "no" is never sent, so this can add the families an
# activity triggers but can never narrow or drop anything.
_ACTIVITY_LABELS: dict[str, str] = {
    "registered_company": "is a registered company that files accounts and corporate tax",
    "licensed_financial_activity": "holds or operates a financial-services licence",
    "holds_customer_funds": "holds or safeguards customer funds",
    "employs_staff": "employs staff and runs payroll",
    "grants_equity": "grants equity, options or share-based awards",
    "takes_foreign_investment": "receives foreign / cross-border investment",
    "intra_group_transactions": "transacts with other group companies (related-party)",
    "holds_personal_data": "processes personal data of individuals",
    "vat_gst_registered": "is VAT / GST registered",
    "has_owners_controllers": "has shareholders / beneficial owners / controllers",
    "sanctions_exposure": "moves money / has customers (sanctions exposure)",
    "conducts_esr_relevant_activity": "conducts an economic-substance relevant activity",
    "audit_required": "is subject to a statutory audit",
}


# UK-specific recall guidance — appended to the discovery context ONLY when the
# entity's jurisdiction is UK. Type-level: it names real, well-known UK filings
# as recall nudges (not jurisdiction guesses); the model still emits only the
# ones that genuinely apply to THIS entity, and the anti-hallucination guard in
# the system prompt still applies.
_UK_FCA_RECALL = (
    "UK RECALL (jurisdiction = UK) — CONSIDER and INCLUDE each of the following "
    "WHERE IT GENUINELY APPLIES to this entity, naming the ACTUAL form/return "
    "(not a generic description), each as its OWN item.\n"
    "Every UK company:\n"
    "- Companies House: annual accounts; confirmation statement; PSC / "
    "beneficial-ownership register updates.\n"
    "- HMRC: Company Tax Return (CT600) AND the corporation-tax payment; VAT "
    "return (if VAT-registered); country-by-country report and transfer-pricing "
    "master & local file (if in scope).\n"
    "- HMRC payroll (if it employs staff / runs payroll) — each as its own item: "
    "PAYE Real-Time-Information Full Payment Submission (FPS, on or before each "
    "payday); Employer Payment Summary (EPS); the monthly PAYE/NIC payment; "
    "P11D and P11D(b) for benefits in kind; and — AS A SEPARATE ITEM, distinct "
    "from the P11D return — the Class 1A NIC PAYMENT (annual, due 22 July); "
    "Employment Related Securities (ERS) "
    "annual return (if it grants shares/options to staff or directors).\n"
    "- The Pensions Regulator: automatic-enrolment re-declaration of compliance "
    "(every 3 years).\n"
    "- ICO: data-protection fee / registration (annual).\n"
    "- OFSI (HM Treasury): annual frozen-asset review (where frozen assets are "
    "held) and sanctions-breach reporting (event-based).\n"
    "If the entity is an FCA-AUTHORISED firm (payment institution, e-money "
    "institution or investment firm) do NOT stop at a generic 'FCA return' — "
    "include the SPECIFIC RegData returns it owes, BY NAME, where applicable:\n"
    "- Capital adequacy: FSA056 (Authorised Payment Institution capital-adequacy "
    "return), or the equivalent own-funds return for EMIs / investment firms.\n"
    "- Safeguarding (if it safeguards customer funds): the monthly safeguarding "
    "return (REP027) AND the annual safeguarding audit report by an independent "
    "auditor.\n"
    "- Financial resilience: FIN073 baseline financial resilience report "
    "(frequency QUARTERLY — submitted each financial quarter, not annually).\n"
    "- Financial crime: REP-CRIM annual financial crime report.\n"
    "- Ownership: REP002 annual controllers report; REP001 annual close-links "
    "report.\n"
    "- Conduct & operations: payments fraud report (REP017, half-yearly); "
    "operational & security risk report (REP018); complaints return "
    "(DISP 1.10B, frequency HALF-YEARLY — two reporting periods a year, not "
    "annual).\n"
    "- Fees: the FCA periodic fee and the annual return of income / fee-tariff "
    "data.\n"
    "- Event-based: change-in-control prior approval / notification; "
    "notification of a significant business change; notification of a breach or "
    "regulatory concern.\n\n"
)


# Type-level recall for e-money / payment institutions, ANY jurisdiction.
# Gated on an EMI/PI signal in the licences or nature of operations (see
# `_emi_signal`). Like the UK block this is RECALL GUIDANCE — it nudges the
# model to consider the prudential/supervisory returns that EMIs characteristically
# owe; the model still generates the actual items (named for the real regulator)
# and they still go through human review. No filing rows are hardcoded.
_EMI_RECALL = (
    "E-MONEY / PAYMENT-INSTITUTION RECALL — this entity holds an e-money or "
    "payment-services authorisation, so beyond the generic corporate/tax/AML "
    "filings it owes PRUDENTIAL and SUPERVISORY returns to its financial "
    "supervisor that are easy to overlook. CONSIDER and INCLUDE each WHERE IT "
    "GENUINELY APPLIES, as its OWN item, named for the actual regulator:\n"
    "- Periodic prudential / own-funds report to the supervisor (commonly "
    "QUARTERLY): own-funds / capital-adequacy calculation, capital-requirement "
    "metrics, average outstanding e-money, and payment-transaction volumes.\n"
    "- Annual prudential / audited supervisory report to the financial "
    "supervisor — this is SEPARATE from filing the annual financial statements "
    "with the company registry; include BOTH as distinct items.\n"
    "- Safeguarding of customer / e-money funds: the periodic safeguarding "
    "return and the independent safeguarding audit, where the regime requires "
    "them.\n"
    "- Periodic AML/CFT reporting to BOTH the financial supervisor AND the "
    "financial-intelligence unit (statistical / questionnaire returns), in "
    "ADDITION to event-based suspicious-transaction reports.\n"
    "- Operational, security-risk, major-incident and fraud reporting under the "
    "payment-services regime; change-in-control / qualifying-holding "
    "notifications.\n"
    "IMPORTANT — these obligation CATEGORIES are well-established for EVERY "
    "e-money / payment institution. Do NOT drop them under the "
    "'omit if unsure' rule just because you are uncertain of the exact local "
    "form name: INCLUDE each that genuinely applies, with a descriptive name "
    "and confidence 'Pending verification - official source check', and let the "
    "human reviewer confirm the precise form. Omitting a known EMI prudential / "
    "AML obligation is a worse error here than naming it provisionally.\n\n"
)


# Jurisdiction recall for Lithuania, mirroring the UK block. Names the real
# authorities (Bank of Lithuania, FCIS/FNTT, VMI, Sodra, Registru centras) so
# the model doesn't fall back to generic descriptions; still recall guidance,
# not seeded data. Payroll is described by FUNCTION (monthly withholding vs the
# annual employee declaration are DISTINCT filings) rather than asserting a
# specific GPM form number, since the exact codes are easy to mis-map.
_LT_RECALL = (
    "LITHUANIA RECALL (jurisdiction = Lithuania) — name the ACTUAL authority and "
    "return for each, as its own item, where it applies:\n"
    "- Bank of Lithuania: the EMI/PI periodic prudential & own-funds report "
    "(quarterly) AND the annual prudential / supervisory report — both separate "
    "from the registry financial statements.\n"
    "- Bank of Lithuania AND the Financial Crime Investigation Service "
    "(FCIS / FNTT): periodic AML/CFT reporting, in addition to "
    "suspicious-transaction reports.\n"
    "- State Tax Inspectorate (VMI): the MONTHLY payroll income-tax withholding "
    "declaration AND the separate ANNUAL employee-by-employee income & "
    "withholding declaration — these are DISTINCT GPM-series filings at "
    "DIFFERENT cadences; list BOTH and match each statutory form code to its "
    "correct cadence (do not reuse one code for both).\n"
    "- VMI: corporate income tax and VAT returns. Registru centras: annual "
    "financial statements. Sodra: social-insurance contribution reporting.\n"
    "These Lithuanian supervisory and tax filings are well-established — "
    "INCLUDE each that applies even if you are unsure of the exact form code, "
    "marking confidence 'Pending verification - official source check' rather "
    "than omitting it.\n\n"
)


# Jurisdiction recall for India. Names the must-not-forget MCA / Income-tax /
# GST / RBI-FEMA / payroll filings — the GST trio is pinned explicitly because
# the model tends to emit GSTR-3B but drop GSTR-1. Recall guidance only.
_IN_RECALL = (
    "INDIA RECALL (jurisdiction = India) — name the ACTUAL authority + statutory "
    "form for each, as its own item, where it applies:\n"
    "- MCA / Registrar of Companies: AOC-4 (annual financial statements); MGT-7 "
    "(annual return); DPT-3 (annual return of deposits); DIR-3 KYC (director KYC, "
    "annual); ADT-1 (auditor appointment, event); MSME-1 (half-yearly dues "
    "return); BEN-2 (significant beneficial ownership, event); DIR-12, INC-22, "
    "PAS-3 (director / registered-office / allotment change filings, event).\n"
    "- Income Tax (CBDT): ITR-6 (annual return); ADVANCE TAX instalments "
    "(QUARTERLY); self-assessment balance payment; Tax Audit Report "
    "(Form 3CA/3CB-3CD); Form 3CEB transfer-pricing accountant's report; Master "
    "File (3CEAA) and CbCR (3CEAD) where the group thresholds are met. TDS "
    "returns, each its OWN quarterly item: 24Q (salary), 26Q (non-salary), 27Q "
    "(payments to non-residents); plus Form 16 / 16A issuance.\n"
    "- GST (GSTN / CBIC) — list ALL of these as DISTINCT items, do NOT collapse "
    "to one: GSTR-1 (outward supplies, MONTHLY or QRMP-quarterly); GSTR-3B "
    "(summary return, MONTHLY); GSTR-9 (annual return) AND GSTR-9C "
    "(reconciliation statement, annual). GSTR-1 is the most commonly missed — "
    "always include it for a GST-registered entity. LUT for zero-rated exports "
    "where services are exported.\n"
    "- RBI / FEMA: Foreign Liabilities & Assets (FLA) return (annual); FC-GPR "
    "(FDI allotment, event); Softex (software/service export, via STPI) where "
    "the entity exports services; ECB / ODI returns where relevant.\n"
    "- Payroll & social security: EPFO PF Electronic Challan cum Return (ECR, "
    "monthly); ESIC contribution (monthly); state Professional Tax return "
    "(monthly/annual — name the state, e.g. Karnataka / Maharashtra); ESOP "
    "perquisite withholding.\n"
    "These Indian filings are well-established — INCLUDE each that applies even "
    "if unsure of the exact form code, marking confidence 'Pending verification "
    "- official source check' rather than omitting it.\n\n"
)


def _emi_signal(nature: str, licenses) -> bool:
    """True when the entity looks like an e-money / payment institution —
    drives whether the EMI prudential-returns recall is injected. Reads the
    nature of operations + each licence's name/type; jurisdiction-neutral."""
    hay = (nature or "").lower() + " " + " ".join(
        f"{l.name or ''} {l.license_type or ''}".lower() for l in licenses
    )
    return any(
        k in hay
        for k in (
            "e-money", "emoney", "electronic money", "emi",
            "payment institution", "payment service", "payment-service",
            "payment service provider", "psp", "remittance", "money transmitt",
        )
    )



# returns the SAME maximal universe of obligations no matter how the Primary
# Activity questions are answered. The primary answers (and their follow-ups)
# only drive the mandatory-vs-conditional-vs-not-applicable classification in
# the assessment step — they never add or remove anything from discovery.
_ALL_ACTIVITIES_BLOCK = (
    "\n\nASSUME ALL ACTIVITIES PRESENT (fixed list — does NOT depend on the "
    "entity's answers): treat the entity as if it performs EVERY one of the "
    "following, and ADD every filing each implies in this jurisdiction. Never "
    "use this list to remove or narrow anything:\n"
    + "\n".join(f"- The entity {label}." for label in _ACTIVITY_LABELS.values())
)


@router.post("/{entity_id}/discover-regulations")
def discover_entity_regulations(
    entity_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    """Entity-level discovery: from the entity's Nature of Operations,
    jurisdiction and ALL its licenses, ask the AI for the MAXIMAL set of
    regulatory obligations (all functions / item types, assume every activity
    present). Discovery is ANSWER-INDEPENDENT: we always assume every primary
    activity is present (see `_ALL_ACTIVITIES_BLOCK`), so the Primary Activity
    answers never add or remove anything here — they only drive the
    mandatory-vs-conditional-vs-not-applicable classification in the assessment
    step. Persists new items as Staging.

    HARD GATE: requires BOTH at least one uploaded license AND a stated nature
    of operations. Without them there's nothing entity-specific to ground on,
    so we refuse rather than emit generic guesses."""
    from compliance_agent.db import License, Rule, RuleStatus
    from compliance_agent.classification import derive_function, owner_team_engine
    from compliance_agent.rule_extractor import (
        extract_rules_from_text,
        is_live,
        RuleExtractorUnavailable,
    )
    from compliance_agent.api.licenses import _read_license_text, _MAX_PROMPT_CHARS
    from compliance_agent.data.authority_urls import lookup as authority_url_lookup

    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found.")
    if not is_live():
        return {"available": False, "created": 0, "notes": "AI is off — set COMPLIANCE_AGENT_LIVE=1 + an API key."}

    juris = entity.jurisdiction_code
    licenses = db.execute(select(License).where(License.entity_id == entity_id)).scalars().all()

    # HARD GATE: both a license on file AND a stated nature of operations are
    # mandatory before we generate anything. The license grounds what the
    # entity is authorised to do; the nature of operations drives the
    # follow-up questions and the mandatory-vs-not classification. Missing
    # either → refuse (HTTP 400) instead of emitting generic guesses.
    if not licenses:
        raise HTTPException(
            status_code=400,
            detail="Upload at least one license for this entity before generating obligations.",
        )
    if not (entity.nature_of_operation or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Set the entity's nature of operations before generating obligations.",
        )

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
            # Match the license-path budget: the whole context is clamped to
            # _MAX_PROMPT_CHARS below (which protects the front-matter facts), so
            # cap per-document at the same budget rather than an arbitrary 8k —
            # otherwise authorised activities deep in a licence never reach the
            # model on this path.
            lic_texts.append(
                f"\n--- LICENSE DOCUMENT: {l.name} ---\n{t[:_MAX_PROMPT_CHARS]}"
            )

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
        "reporting obligations.\n"
        "Be EXHAUSTIVE on the BASELINE obligations every company of this legal "
        "type owes in this jurisdiction — even when no specific activity "
        "triggers them. List each as its OWN item (do not summarise), and when "
        "unsure whether one applies, INCLUDE it marked Conditional rather than "
        "omitting it:\n"
        "- Finance / Tax: corporate / income tax return AND its balance payment "
        "AND instalments; VAT / GST / sales-tax registration and periodic "
        "returns; annual financial statements and audit / accounts filing; "
        "payroll withholding remittances AND the separate annual "
        "employee-by-employee income / withholding declaration (these are "
        "DISTINCT filings at different cadences — include both); "
        "social-security / pension contributions; transfer-pricing "
        "documentation where there are related-party transactions.\n"
        "- Legal / Corporate: company-registry annual return / confirmation "
        "statement; persons-with-significant-control / beneficial-ownership "
        "register; statutory registers; notifications of changes to directors "
        "or registered office.\n"
        "- Compliance / AML: registration / renewal with the AML supervisor; "
        "AML compliance programme, risk assessment and periodic review; "
        "suspicious-activity and threshold transaction reporting; sanctions "
        "screening; data-protection registration / fee where the jurisdiction "
        "requires it.\n"
        "Then add ANY FURTHER activity-specific obligations the nature of "
        "operations, a CONFIRMED ACTIVITY below, or a license triggers. Only "
        "leave out items that clearly do NOT apply to this legal type / "
        "jurisdiction. One entry per distinct item.\n\n"
        # Recall guidance for regulated money-movement businesses. The model
        # reliably lists the generic corporate/tax/payroll filings but forgets
        # the transaction-level AML reports and the payments-regulator returns
        # that are the CORE obligations of an MSB/PSP. This is type-level
        # guidance only (no jurisdiction-specific form names) — it nudges recall
        # without asserting any specific filing exists.
        "REGULATED-ACTIVITY CHECKLIST — if the nature of operations or the "
        "licences indicate the entity is a money-services business, money "
        "transmitter, remittance provider, foreign-exchange dealer, "
        "virtual-currency / crypto dealer, or payment service provider, do NOT "
        "stop at the generic corporate/tax/payroll filings. Make sure you have "
        "CONSIDERED and included (only where they genuinely apply to THIS "
        "entity) the obligations these businesses characteristically owe:\n"
        "- Transaction reports to the AML/financial-intelligence regulator: "
        "large-cash transaction reports, large virtual-currency transaction "
        "reports, electronic / cross-border funds-transfer reports above the "
        "reporting threshold, suspicious-transaction reports, and "
        "terrorist-property reports.\n"
        "- AML programme duties: compliance programme + risk assessment, the "
        "periodic effectiveness review, ongoing monitoring, customer "
        "identification (KYC), PEP and sanctions screening, and record-keeping.\n"
        "- Registration / renewal with the AML regulator.\n"
        "- For payment service providers: any periodic or annual report to the "
        "payments regulator under the applicable retail-payments / "
        "payment-services regime.\n"
        "These are frequently the MOST important obligations for such a business "
        "and the easiest to overlook — include them when the entity clearly "
        "performs these activities.\n\n"
        + (_UK_FCA_RECALL if (juris or "").strip().lower() == "uk" else "")
        + (_EMI_RECALL if _emi_signal(entity.nature_of_operation, licenses) else "")
        + (_LT_RECALL if (juris or "").strip().lower() == "lithuania" else "")
        + (_IN_RECALL if (juris or "").strip().lower() == "india" else "")
        + f"ENTITY: {entity.name}\n"
        f"Jurisdiction: {juris}\n"
        f"Legal type: {entity.legal_type or '(unknown)'}\n"
        f"Fiscal year end: {entity.fiscal_year_end or '(not set)'} — express any "
        f"year-end-relative deadline (e.g. corporate tax, annual accounts) "
        f"relative to THIS date.\n"
        f"Nature of operations: {entity.nature_of_operation or '(not provided)'}"
        + _ALL_ACTIVITIES_BLOCK
        + "\n\nLICENSES HELD:\n" + "\n".join(lic_lines) + "\n" + "".join(lic_texts)
    )[:_MAX_PROMPT_CHARS]

    try:
        result = extract_rules_from_text(context, jurisdiction_hint=juris)
    except RuleExtractorUnavailable as exc:
        return {"available": False, "created": 0, "notes": str(exc)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Claude call failed: {exc}") from exc

    # First collapse duplicates that earlier refreshes persisted, so the
    # discovered list stops showing repeats of the same filing. Then dedupe new
    # candidates on (normalized name/form + cadence): an exact repeat is
    # skipped, but a genuinely different-cadence filing of the same name is kept.
    deduped = _collapse_duplicate_rules(db, entity)
    existing: set = set()
    for r in _entity_rules_fresh(db, entity):
        existing |= _dup_signatures(r.name, r.form_name, r.frequency, r.jurisdiction_code)
    created: list = []
    already_present = 0  # candidates skipped because they already exist here
    for cand in result.rules:
        sigs = _dup_signatures(cand.name, cand.form_name, cand.frequency, juris)
        if not sigs or sigs & existing:
            already_present += 1
            continue
        existing |= sigs
        rule = Rule(
            name=cand.name,
            jurisdiction_code=(juris or "xx")[:16],
            category=cand.category,
            area=cand.area,
            form_name=cand.form_name,
            authority=cand.authority,
            # Official authority website (curated, real URLs) so a reviewer can
            # verify the filing. Authority-level, not the exact form page.
            source_url=authority_url_lookup(cand.authority),
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
                else owner_team_engine(
                    cand.name, cand.authority, cand.category, cand.area,
                    getattr(cand, "triggering_activity", None),
                )
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
    # Collapse VAT/GST returns to a single entry stamped with the answered
    # cadence (a return is filed at one cadence, so Monthly + Quarterly variants
    # are a duplicate). Runs after the add so it catches newly-created variants.
    deduped += _collapse_vat_returns(db, entity)
    db.flush()
    # Final pass — AI clustering catches the SEMANTIC duplicates the signature
    # heuristics miss (synonymous names, different authority spellings,
    # generic-vs-specific). Only ever removes pure discovered drafts. This also
    # stops the additive refresh from accumulating naming variants across runs.
    deduped += _ai_collapse_duplicates(db, entity)
    db.flush()
    # Refresh is ADDITIVE: a candidate that already exists is skipped (counted in
    # already_present), net-new ones are added, and genuine duplicate ROWS are
    # collapsed above. We deliberately do NOT drop previously-discovered drafts
    # just because this (non-deterministic) run didn't reproduce them — that made
    # the list churn/shrink across refreshes. Wrong drafts are removed manually.
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
    logger.info(
        "DISCOVERY entity=%s (%s): model returned %d candidate(s) -> created %d, "
        "already_present %d, duplicates_removed %d. notes=%r",
        entity_id, entity.name, len(result.rules), len(created),
        already_present, deduped, result.notes,
    )
    log_activity(
        db, actor_id=user.id, action="entity.discovered_regulations",
        target_type="entity", target_id=entity_id,
        payload={"created": len(created), "duplicates_removed": deduped},
    )
    db.commit()
    return {
        "available": True,
        "created": len(created),
        # Names of the filings that were NOT already present and have now been
        # added — so the admin sees exactly what's new vs what was already
        # tracked. A second run (or a different function's owner) only ever
        # adds what's missing; everything else is counted in already_present.
        "added": [r.name for r in created],
        "already_present": already_present,
        "duplicates_removed": deduped,
        "notes": result.notes,
    }


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
    from compliance_agent.api.licenses import _read_license_text, _MAX_PROMPT_CHARS

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
    # Feed the licence DOCUMENT TEXT, not just metadata: the generator must see
    # what the licence/regulator/authorised-activities already establish so it
    # does NOT re-ask facts that are extractable from the documents.
    lic_texts: list[str] = []
    for l in licenses:
        try:
            t = _read_license_text(l)
        except Exception:  # noqa: BLE001
            t = ""
        if t and len(t.strip()) >= 200:
            lic_texts.append(f"\n--- LICENSE DOCUMENT: {l.name} ---\n{t[:8000]}")
    # Primary answers already on file — the generator must never re-ask these.
    profile = entity.finance_profile or {}
    known_block = "\n".join(
        f"- {k}: {v}" for k, v in profile.items() if v not in (None, "")
    ) or "(none answered yet)"
    items_block = "\n".join(f"- {r.form_name} ({r.category})" for r in discovered) or "(none yet)"
    context = (
        f"ENTITY: {entity.name}\n"
        f"Jurisdiction: {entity.jurisdiction_code}\n"
        f"Legal type: {entity.legal_type or '(unknown)'}\n"
        f"Nature of operations: {entity.nature_of_operation or '(not provided)'}\n\n"
        f"LICENSES / REGISTRATIONS HELD:\n{lic_block}\n"
        + "".join(lic_texts)
        + f"\n\nKNOWN PRIMARY FACTS (already answered — never re-ask):\n{known_block}\n\n"
        f"REGULATORY ITEMS ALREADY DISCOVERED (validate applicability only — never remove):\n{items_block}\n"
    )[:_MAX_PROMPT_CHARS]

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
            "multi_select": bool(getattr(q, "multi_select", False)),
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
