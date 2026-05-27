"""License CRUD + applicable-regulation matching.

A license is an authorisation an entity holds from a regulator. The most
useful question we answer is: "for this license, which filings do you owe?"

Matching rules to a license:
  - Required: same jurisdiction_code.
  - Strong match: rule's authority contains a token from the license's
    authority OR license_type (case-insensitive). These are surfaced as
    "Directly applicable".
  - Soft match: rule is attached to the same entity but doesn't strong-match.
    Surfaced as "Other obligations for this entity".

  GET    /api/licenses                       - list (filters: entity_id, jurisdiction_code, expiring_within_days)
  POST   /api/licenses                       - admin: create (multipart, optional file)
  GET    /api/licenses/{id}                  - detail (no rules)
  GET    /api/licenses/{id}/applicable-rules - rules grouped by relevance
  PATCH  /api/licenses/{id}                  - admin: edit
  DELETE /api/licenses/{id}                  - admin: delete (also drops file)
  GET    /api/licenses/{id}/download         - stream the license file (if any)
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from compliance_agent import storage
from compliance_agent.api._helpers import log_activity
from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.db import (
    Entity,
    License,
    Obligation,
    ObligationStatus,
    Rule,
    RuleStatus,
    User,
    get_session,
)


router = APIRouter(prefix="/api/licenses", tags=["licenses"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LicenseOut(_Base):
    id: int
    entity_id: int
    entity_name: str
    name: str
    license_type: str
    authority: str
    jurisdiction_code: str
    license_number: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    notes: Optional[str] = None
    has_file: bool
    filename: Optional[str] = None
    size_bytes: int = 0
    content_type: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Lightweight status hint computed at read time so the list view can
    # colour-code rows without a second call.
    expiry_status: str  # "valid" | "expiring" | "expired" | "unknown"
    days_to_expiry: Optional[int] = None


class LicenseAssignee(_Base):
    id: int
    email: str
    full_name: Optional[str] = None


class LicenseRuleHit(_Base):
    id: int
    name: str
    form_name: str
    authority: str
    category: str
    area: str
    frequency: str
    due_date_rule: str
    payment_rule: Optional[str] = None
    applicability: str
    relevance: str  # "direct" | "entity"
    match_reason: Optional[str] = None
    # Tracking — the next upcoming obligation for (this rule, license.entity).
    next_obligation_id: Optional[int] = None
    next_due_date: Optional[date] = None
    next_status: Optional[str] = None
    next_assignee: Optional[LicenseAssignee] = None
    days_to_next: Optional[int] = None


class ApplicableRulesResponse(_Base):
    license_id: int
    direct: list[LicenseRuleHit]
    entity_other: list[LicenseRuleHit]
    # Aggregate roll-up so the UI can show counts without re-counting on the
    # client.
    counts: dict[str, int] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]+")
# Words too generic to use as a match signal (otherwise every rule looks
# "directly applicable" to every license).
_STOPWORDS = {
    "the", "and", "for", "of", "to", "in", "on", "a", "an",
    "authority", "ministry", "department", "office", "regulator",
    "tax", "national", "federal", "service", "services", "central",
    "general", "global", "government", "republic", "council",
    "agency", "bureau", "company", "commission",
    "ltd", "inc", "llc", "corp", "plc", "gmbh", "co",
    "license", "licence", "registration", "regulatory",
    "form", "report", "return",
    # Country labels — too generic, since every jurisdictional rule
    # references its own country in name/authority.
    "uae", "ind", "ksa", "sgp", "lux", "gbr",
    "india", "indian",
    "uk", "britain", "british",
    "usa", "america", "american",
    "europe", "european",
    "lithuanian", "singapore", "singaporean", "canadian",
}


def _tokens(*texts: str) -> set[str]:
    out: set[str] = set()
    for t in texts:
        if not t:
            continue
        for m in _TOKEN_RE.findall(t):
            tok = m.lower()
            if len(tok) >= 3 and tok not in _STOPWORDS:
                out.add(tok)
    return out


def _expiry_status(expiry: Optional[date]) -> tuple[str, Optional[int]]:
    if expiry is None:
        return "unknown", None
    today = date.today()
    days = (expiry - today).days
    if days < 0:
        return "expired", days
    if days <= 60:
        return "expiring", days
    return "valid", days


def _serialize(lic: License) -> LicenseOut:
    status, days = _expiry_status(lic.expiry_date)
    return LicenseOut(
        id=lic.id,
        entity_id=lic.entity_id,
        entity_name=lic.entity.name if lic.entity else "",
        name=lic.name,
        license_type=lic.license_type or "",
        authority=lic.authority,
        jurisdiction_code=lic.jurisdiction_code,
        license_number=lic.license_number,
        issue_date=lic.issue_date,
        expiry_date=lic.expiry_date,
        notes=lic.notes,
        has_file=bool(lic.storage_path),
        filename=lic.filename,
        size_bytes=lic.size_bytes,
        content_type=lic.content_type,
        created_at=lic.created_at,
        updated_at=lic.updated_at,
        expiry_status=status,
        days_to_expiry=days,
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.get("", response_model=list[LicenseOut])
def list_licenses(
    entity_id: Optional[int] = Query(None),
    jurisdiction_code: Optional[str] = Query(None),
    expiring_within_days: Optional[int] = Query(
        None, ge=0, description="Only show licenses expiring in <= N days."
    ),
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[LicenseOut]:
    stmt = select(License).order_by(
        License.expiry_date.is_(None), License.expiry_date, License.name
    )
    if entity_id is not None:
        stmt = stmt.where(License.entity_id == entity_id)
    if jurisdiction_code:
        stmt = stmt.where(License.jurisdiction_code == jurisdiction_code)
    if expiring_within_days is not None:
        cutoff = date.today() + timedelta(days=expiring_within_days)
        stmt = stmt.where(
            License.expiry_date.is_not(None),
            License.expiry_date <= cutoff,
        )
    rows = db.execute(stmt).scalars().all()
    return [_serialize(r) for r in rows]


@router.get("/{license_id}", response_model=LicenseOut)
def get_license(
    license_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> LicenseOut:
    lic = db.get(License, license_id)
    if lic is None:
        raise HTTPException(status_code=404, detail="License not found.")
    return _serialize(lic)


def _parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Date '{raw}' must be in YYYY-MM-DD format.",
        ) from e


@router.post("", response_model=LicenseOut, status_code=201)
def create_license(
    entity_id: int = Form(...),
    name: str = Form(...),
    authority: str = Form(...),
    jurisdiction_code: str = Form(...),
    license_type: str = Form(""),
    license_number: Optional[str] = Form(None),
    issue_date: Optional[str] = Form(None),
    expiry_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> LicenseOut:
    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found.")

    lic = License(
        entity_id=entity_id,
        name=name.strip(),
        license_type=license_type.strip(),
        authority=authority.strip(),
        jurisdiction_code=jurisdiction_code.strip().lower(),
        license_number=license_number.strip() if license_number else None,
        issue_date=_parse_date(issue_date),
        expiry_date=_parse_date(expiry_date),
        notes=notes,
        created_by_id=user.id,
    )

    if file is not None and file.filename:
        storage_path, size = storage.save_bytes(
            entity_id, file.filename, file.file
        )
        lic.filename = file.filename
        lic.storage_path = storage_path
        lic.size_bytes = size
        lic.content_type = file.content_type

    db.add(lic)
    db.flush()
    log_activity(
        db,
        actor_id=user.id,
        action="license.created",
        target_type="license",
        target_id=lic.id,
        payload={
            "entity_id": entity_id,
            "name": lic.name,
            "authority": lic.authority,
        },
    )
    db.commit()
    db.refresh(lic)
    return _serialize(lic)


class LicenseUpdate(BaseModel):
    name: Optional[str] = None
    license_type: Optional[str] = None
    authority: Optional[str] = None
    jurisdiction_code: Optional[str] = None
    license_number: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    notes: Optional[str] = None


@router.patch("/{license_id}", response_model=LicenseOut)
def update_license(
    license_id: int,
    payload: LicenseUpdate,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> LicenseOut:
    lic = db.get(License, license_id)
    if lic is None:
        raise HTTPException(status_code=404, detail="License not found.")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(lic, k, v)
    log_activity(
        db,
        actor_id=user.id,
        action="license.updated",
        target_type="license",
        target_id=lic.id,
        payload=data,
    )
    db.commit()
    db.refresh(lic)
    return _serialize(lic)


@router.delete("/{license_id}", status_code=204)
def delete_license(
    license_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> None:
    lic = db.get(License, license_id)
    if lic is None:
        raise HTTPException(status_code=404, detail="License not found.")
    path = lic.storage_path
    db.delete(lic)
    log_activity(
        db,
        actor_id=user.id,
        action="license.deleted",
        target_type="license",
        target_id=license_id,
    )
    db.commit()
    if path:
        try:
            storage.delete(path)
        except Exception:  # noqa: BLE001
            pass


@router.get("/{license_id}/download")
def download_license_file(
    license_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    lic = db.get(License, license_id)
    if lic is None or not lic.storage_path:
        raise HTTPException(status_code=404, detail="License file not found.")
    stream = storage.open_read(lic.storage_path)
    filename = lic.filename or f"license-{license_id}"
    return StreamingResponse(
        stream,
        media_type=lic.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Applicable regulations
# ---------------------------------------------------------------------------
@router.get("/{license_id}/applicable-rules", response_model=ApplicableRulesResponse)
def applicable_rules(
    license_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> ApplicableRulesResponse:
    lic = db.get(License, license_id)
    if lic is None:
        raise HTTPException(status_code=404, detail="License not found.")

    # 1. Candidate pool: production rules in this jurisdiction.
    pool = (
        db.execute(
            select(Rule)
            .where(
                Rule.jurisdiction_code == lic.jurisdiction_code,
                Rule.status == RuleStatus.production,
            )
            .order_by(Rule.category, Rule.form_name)
        )
        .scalars()
        .all()
    )

    license_tokens = _tokens(lic.authority, lic.license_type, lic.name)

    # 2. Rules already attached to the entity — used to flag "Other obligations".
    entity_rule_ids: set[int] = set()
    entity = lic.entity
    if entity is not None:
        entity_rule_ids = {r.id for r in entity.rules}

    # 3. Tracking — for each rule, find the next upcoming, not-yet-completed
    # obligation against THIS license's entity. One query, then bucket by
    # rule_id.
    today_d = date.today()
    next_by_rule: dict[int, Obligation] = {}
    if entity is not None:
        rows = (
            db.execute(
                select(Obligation)
                .options(
                    joinedload(Obligation.assignee),
                )
                .where(
                    Obligation.entity_id == entity.id,
                    Obligation.status.notin_(
                        [
                            ObligationStatus.completed,
                            ObligationStatus.not_applicable,
                        ]
                    ),
                    Obligation.due_date >= today_d,
                )
                .order_by(Obligation.rule_id, Obligation.due_date)
            )
            .scalars()
            .unique()
            .all()
        )
        for ob in rows:
            # First encounter per rule_id is the soonest due_date (ASC order).
            if ob.rule_id not in next_by_rule:
                next_by_rule[ob.rule_id] = ob

    def _hit(rule: Rule, *, relevance: str, match_reason: str) -> LicenseRuleHit:
        ob = next_by_rule.get(rule.id)
        assignee = None
        if ob is not None and ob.assignee is not None:
            assignee = LicenseAssignee(
                id=ob.assignee.id,
                email=ob.assignee.email,
                full_name=ob.assignee.full_name,
            )
        return LicenseRuleHit(
            id=rule.id,
            name=rule.name,
            form_name=rule.form_name,
            authority=rule.authority,
            category=rule.category,
            area=rule.area,
            frequency=rule.frequency,
            due_date_rule=rule.due_date_rule,
            payment_rule=rule.payment_rule,
            applicability=rule.applicability.value if rule.applicability else "",
            relevance=relevance,
            match_reason=match_reason,
            next_obligation_id=ob.id if ob else None,
            next_due_date=ob.due_date if ob else None,
            next_status=ob.status.value if ob and ob.status else None,
            next_assignee=assignee,
            days_to_next=((ob.due_date - today_d).days if ob else None),
        )

    direct: list[LicenseRuleHit] = []
    entity_other: list[LicenseRuleHit] = []

    for rule in pool:
        rule_tokens = _tokens(rule.authority, rule.category, rule.area)
        shared = license_tokens & rule_tokens
        is_attached = rule.id in entity_rule_ids
        if shared:
            direct.append(
                _hit(
                    rule,
                    relevance="direct",
                    match_reason=f"matched on: {', '.join(sorted(shared))}",
                )
            )
        elif is_attached:
            entity_other.append(
                _hit(rule, relevance="entity", match_reason="attached to this entity")
            )

    # Roll-up counts so the UI can show "5 unassigned · 3 in progress · …"
    counts: dict[str, int] = {
        "total": len(direct) + len(entity_other),
        "not_scheduled": 0,
        "unassigned": 0,
        "not_started": 0,
        "in_progress": 0,
        "pending_review": 0,
        "completed_next": 0,  # next upcoming was completed — rare; left for sanity
    }
    for hit in (*direct, *entity_other):
        if hit.next_obligation_id is None:
            counts["not_scheduled"] += 1
            continue
        if hit.next_assignee is None:
            counts["unassigned"] += 1
        status_key = hit.next_status or "not_started"
        if status_key in counts:
            counts[status_key] += 1

    return ApplicableRulesResponse(
        license_id=license_id,
        direct=direct,
        entity_other=entity_other,
        counts=counts,
    )
