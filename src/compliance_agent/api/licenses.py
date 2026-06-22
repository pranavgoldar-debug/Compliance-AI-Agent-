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

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete as sa_delete, or_, select, update as sa_update
from sqlalchemy.orm import Session, joinedload

from compliance_agent import storage
from compliance_agent.classification import (
    derive_function,
    derive_tax_type,
    keep_function,
)
from compliance_agent.api._helpers import log_activity
from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.db import (
    Activity,
    Applicability,
    Comment,
    Department,
    Document,
    Entity,
    License,
    Notification,
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
    responsible_function: Optional[str] = None
    plain_description: Optional[str] = None
    tax_type: str = "Not a Tax"
    relevance: str  # "direct" | "entity"
    match_reason: Optional[str] = None
    # Tracking — the next upcoming obligation for (this rule, license.entity).
    next_obligation_id: Optional[int] = None
    next_due_date: Optional[date] = None
    # Estimated next deadline derived from the rule's frequency — shown the
    # moment a licence is uploaded, before anything is scheduled, so every
    # obligation carries a date.
    projected_due_date: Optional[date] = None
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


_FORM_CODE_RE = re.compile(r"[A-Z0-9][A-Z0-9]*(?:[-/][A-Z0-9]+)*")


def _form_code(text: str) -> str:
    """Pull official form code(s) (letter+digit tokens like CT600, FSA056,
    GSTR-3B) out of a filing/form name. Mirror of the frontend extractFormCode."""
    if not text:
        return ""
    seen: list[str] = []
    for tok in _FORM_CODE_RE.findall(text):
        if (
            any(c.isdigit() for c in tok)
            and any(c.isalpha() for c in tok)
            and 3 <= len(tok) <= 14
            and tok not in seen
        ):
            seen.append(tok)
    return " / ".join(seen)


def _rule_key(name: str, form_name: str) -> tuple:
    """Dedup identity for a filing. Uses the form code ONLY when it leads the
    name (e.g. 'CT600 — Corporation Tax Return') — a code merely mentioned in
    passing ('PAYE RTI … + P11D', 'EBA Fraud Reporting … under PSD2') must NOT
    collapse two genuinely different filings, so those fall back to the name."""
    code = (_form_code(form_name or "").split(" / ")[0]).strip()
    lead = re.sub(r"^[^A-Za-z0-9]+", "", form_name or "")
    if code and lead.upper().startswith(code.upper()):
        return ("code", code.lower())
    return ("name", re.sub(r"[^a-z0-9]+", "", (name or form_name or "").lower()))


def _dedupe_rules(rules: list) -> list:
    """Collapse near-duplicate rules so the same filing doesn't appear twice
    (e.g. two CT600 rows). Conservative — see _rule_key. Keeps the first."""
    seen: set = set()
    out: list = []
    for r in rules:
        key = _rule_key(r.name or "", r.form_name or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
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
        storage_path, size = storage.save_bytes(entity_id, file.filename, file.file)
        lic.filename = file.filename
        lic.storage_path = storage_path
        lic.size_bytes = size
        lic.content_type = file.content_type

    db.add(lic)
    db.flush()

    # Surface the uploaded license file in the Documents section too (reuses
    # the same stored blob) so it shows on the entity's Documents tab.
    if lic.storage_path:
        from compliance_agent.db import Document, DocumentCategory

        db.add(
            Document(
                entity_id=entity_id,
                filename=lic.filename or "license",
                storage_path=lic.storage_path,
                content_type=lic.content_type,
                size_bytes=lic.size_bytes,
                category=DocumentCategory.filings,
                tags="license",
                uploaded_by_id=user.id,
            )
        )

    # Auto-schedule on upload: put every applicable filing for this licence's
    # jurisdiction straight onto the calendar, so the admin doesn't have to
    # schedule them one by one. (FINANCE_ONLY narrows this to Finance filings.)
    auto_scheduled = 0
    try:
        auto_scheduled, _, _ = _schedule_filings_for_license(
            db, lic, mandatory_only=False
        )
    except Exception:  # noqa: BLE001 — never block license creation on this
        auto_scheduled = 0

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
            "auto_scheduled": auto_scheduled,
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
        # JSON-safe dump (dates -> ISO strings) so the JSON activity payload
        # doesn't choke on date objects (was a 500 on edit).
        payload=payload.model_dump(exclude_unset=True, mode="json"),
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

    # Remove this licence's calendar entries (the obligations it auto-scheduled)
    # plus their dependent rows — but LEAVE the underlying rules in the
    # catalogue, so re-adding the licence later just re-schedules them.
    ob_ids = (
        db.execute(select(Obligation.id).where(Obligation.license_id == license_id))
        .scalars()
        .all()
    )
    removed_obligations = len(ob_ids)
    if ob_ids:
        db.execute(sa_delete(Comment).where(Comment.obligation_id.in_(ob_ids)))
        db.execute(
            sa_delete(Notification).where(Notification.obligation_id.in_(ob_ids))
        )
        db.execute(
            sa_update(Document)
            .where(Document.obligation_id.in_(ob_ids))
            .values(obligation_id=None)
        )
        db.execute(
            sa_delete(Activity).where(
                Activity.target_type == "obligation",
                Activity.target_id.in_(ob_ids),
            )
        )
        db.execute(sa_delete(Obligation).where(Obligation.id.in_(ob_ids)))

    db.delete(lic)
    log_activity(
        db,
        actor_id=user.id,
        action="license.deleted",
        target_type="license",
        target_id=license_id,
        payload={"removed_obligations": removed_obligations},
    )
    db.commit()
    if path:
        try:
            storage.delete(path)
        except Exception:  # noqa: BLE001
            pass


@router.post("/clear-all")
def clear_all_licenses(
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> dict:
    """Admin-only: delete EVERY license (rows + files) so the admin can
    re-upload from scratch. Does not touch obligations already on the
    calendar."""
    lics = db.execute(select(License)).scalars().all()
    paths = [l.storage_path for l in lics if l.storage_path]
    count = len(lics)
    for l in lics:
        db.delete(l)
    log_activity(
        db,
        actor_id=user.id,
        action="licenses.cleared_all",
        target_type="license",
        target_id=None,
        payload={"deleted": count},
    )
    db.commit()
    for p in paths:
        try:
            storage.delete(p)
        except Exception:  # noqa: BLE001
            pass
    return {"deleted": count}
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
# AI extraction — read the uploaded license file, ask Claude to surface
# every compliance obligation a holder of this license owes, and return
# them as CandidateRule rows the admin can review + materialise.
# ---------------------------------------------------------------------------
class LicenseAIExtractResponse(BaseModel):
    available: bool
    license_id: int
    jurisdiction_hint: Optional[str] = None
    extracted_chars: int = 0
    from_document: bool = True
    candidates: list = []  # list[CandidateRule] — typed late to avoid cycle
    notes: Optional[str] = None
    # Debug-only discovery audit (extracted facts + obligation counts by source).
    # Populated only when COMPLIANCE_AGENT_DISCOVERY_DEBUG=1; production UI ignores it.
    debug_audit: Optional[dict] = None


_MAX_EXTRACT_BYTES = 4_000_000   # ~4 MB of source text — enough for any single licence
_MAX_PROMPT_CHARS = 60_000        # rough char cap to keep Claude prompt manageable


# Find Regulations qualifying questions. Keys match the frontend questionnaire;
# each maps an answer value to a human line for the prompt. The answers drive
# Mandatory vs Conditional only — no filing is ever dropped.
#
# This dict is OPTIONAL — just nicer labels. `_build_profile_block` falls back
# to humanising any unknown key/value, so questions added on the frontend work
# without touching this file.

# Generic answer-value → human text, used when a key isn't in _PROFILE_QUESTIONS
# (or its value isn't listed). Keeps the frontend the single source of truth.
_VALUE_LABELS: dict[str, str] = {
    "yes": "yes",
    "no": "no",
    "unsure": "not sure",
    "na": "not applicable",
    "below": "below threshold",
    "above": "above threshold",
    "monthly": "monthly",
    "quarterly": "quarterly",
    "annual": "annual",
}


def _humanize_key(key: str) -> str:
    """Turn a profile key like 'related_party' into 'Related party'."""
    return key.replace("_", " ").strip().capitalize()


_PROFILE_QUESTIONS: dict[str, dict] = {
    "registered_company": {
        "label": "Registered company that files accounts + corporate tax",
        "values": {"yes": "yes", "no": "no"},
    },
    "ct_income_band": {
        "label": "Taxable income vs the local corporate-tax threshold",
        "values": {"below": "below threshold", "above": "above threshold", "unsure": "not sure"},
    },
    "licensed_financial_activity": {
        "label": "Holds / operates a financial-services licence",
        "values": {"yes": "yes", "no": "no"},
    },
    "holds_customer_funds": {
        "label": "Holds or safeguards customer funds",
        "values": {"yes": "yes", "no": "no"},
    },
    "employs_staff": {
        "label": "Employs staff and runs payroll directly",
        "values": {"yes": "yes", "no": "no"},
    },
    "wps": {
        "label": "Salaries paid via the Wage Protection System (WPS)",
        "values": {"yes": "yes", "no": "no"},
    },
    "social_security": {
        "label": "Contributes to pension / social security",
        "values": {"yes": "yes", "no": "no"},
    },
    "grants_equity": {
        "label": "Grants equity, options or share-based awards",
        "values": {"yes": "yes", "no": "no"},
    },
    "takes_foreign_investment": {
        "label": "Receives foreign / cross-border investment",
        "values": {"yes": "yes", "no": "no"},
    },
    "intra_group_transactions": {
        "label": "Transacts with other group companies",
        "values": {"yes": "yes", "no": "no"},
    },
    "tp_threshold": {
        "label": "Related-party transactions vs the TP documentation threshold",
        "values": {"below": "below threshold", "above": "above threshold", "unsure": "not sure"},
    },
    "holds_personal_data": {
        "label": "Processes personal data of individuals",
        "values": {"yes": "yes", "no": "no"},
    },
    "vat_gst_registered": {
        "label": "VAT / GST registered",
        "values": {"yes": "yes", "no": "no", "unsure": "not sure"},
    },
    "vat_frequency": {
        "label": "VAT / GST return frequency",
        "values": {"monthly": "monthly", "quarterly": "quarterly", "annual": "annual"},
    },
    "has_owners_controllers": {
        "label": "Has shareholders / controllers (beneficial owners)",
        "values": {"yes": "yes", "no": "no"},
    },
    "sanctions_exposure": {
        "label": "Moves money / has customers (sanctions exposure)",
        "values": {"yes": "yes", "no": "no"},
    },
    "conducts_esr_relevant_activity": {
        "label": 'Conducts a "relevant activity" under ESR',
        "values": {"yes": "yes", "no": "no"},
    },
    "esr_income": {
        "label": "Earns income from the ESR relevant activity",
        "values": {"yes": "yes", "no": "no"},
    },
    "audit_required": {
        "label": "Statutory audit required (regulator / company size)",
        "values": {"yes": "yes", "no": "no", "unsure": "not sure"},
    },
}


def _build_profile_block(profile: Optional[dict]) -> str:
    """Render the entity's qualifying-question answers into a prompt block that
    tells Claude how to use them for applicability. Empty when no profile.

    Generic: renders WHATEVER keys/values the profile contains. `_PROFILE_
    QUESTIONS` is only an optional nicer-label override — new questions added on
    the frontend show up here automatically (key/value humanised), so the
    questionnaire stays the single source of truth."""
    if not profile:
        return ""
    lines: list[str] = []
    for key, raw in profile.items():
        if raw in (None, ""):
            continue
        spec = _PROFILE_QUESTIONS.get(key)
        label = spec["label"] if spec else _humanize_key(key)
        if spec and str(raw) in spec["values"]:
            human = spec["values"][str(raw)]
        else:
            human = _VALUE_LABELS.get(str(raw), str(raw))
        lines.append(f"- {label}: {human}")
    if not lines:
        return ""
    return (
        "\n\nCOMPANY PROFILE (admin-provided — use this to set each filing's "
        "applicability):\n"
        + "\n".join(lines)
        + "\n\nApply this profile to set applicability ONLY — do NOT omit or "
        "drop any filing; keep the full finance list and just label each one:\n"
        "- Mark a filing MANDATORY when the profile makes it clearly required "
        "— e.g. VAT/GST-registered -> VAT/GST return is Mandatory; runs "
        "payroll -> payroll / WPS / withholding returns are Mandatory; "
        "related-party or cross-border transactions -> transfer-pricing "
        "documentation is Mandatory; revenue above the threshold -> "
        "threshold-triggered filings are Mandatory.\n"
        "- Mark a filing CONDITIONAL when the profile says it does NOT apply, "
        "is 'not applicable', or is silent / 'not sure' — e.g. NOT "
        "VAT-registered -> VAT return is Conditional (not dropped); no payroll "
        "-> payroll returns Conditional. When an answer is 'not applicable', "
        "add an applicability_note saying the filing does not currently apply "
        "to this entity. Use the applicability_note to say what would trigger "
        "each conditional filing.\n"
        "Every finance filing still appears in the output regardless of the "
        "profile — the profile only changes Mandatory vs Conditional."
    )


def _read_license_text(lic: License) -> str:
    """Pull plain text out of the uploaded license file. PDFs go through
    pypdf; text-like uploads pass through. Returns '' if no file."""
    if not lic.storage_path:
        return ""
    data = storage.read_bytes(lic.storage_path)
    if not data or len(data) > _MAX_EXTRACT_BYTES:
        return ""

    name = (lic.filename or lic.storage_path or "").lower()
    try:
        if name.endswith(".pdf"):
            import io

            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            return "\n\n".join((p.extract_text() or "") for p in reader.pages)
        # Best-effort text read for .txt / .md / .csv etc. Binary files (e.g.
        # an image) will just return empty after decode-with-replace.
        return data.decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# Pre-fill the Add-License form by reading the uploaded PDF with Claude.
# Stateless — nothing is saved; we just return suggested field values + a
# best-guess entity match for the admin to review before creating.
# ---------------------------------------------------------------------------
class LicenseAnalyzeResponse(BaseModel):
    available: bool
    notes: Optional[str] = None
    suggested_entity_id: Optional[int] = None
    entity_name: Optional[str] = None
    name: Optional[str] = None
    license_type: Optional[str] = None
    authority: Optional[str] = None
    jurisdiction_code: Optional[str] = None
    license_number: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None


def _extract_text_from_upload(filename: str, data: bytes) -> str:
    """Pull plain text out of raw uploaded bytes (PDF via pypdf, else decode)."""
    name = (filename or "").lower()
    try:
        if name.endswith(".pdf"):
            import io

            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            return "\n\n".join((p.extract_text() or "") for p in reader.pages)
        return data.decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""


def _match_entity(db: Session, *, entity_name: Optional[str], jurisdiction_code: Optional[str]):
    """Best-effort match an extracted licensee name to an existing entity."""
    if not entity_name:
        return None
    name_lc = entity_name.strip().lower()
    entities = (
        db.execute(select(Entity).where(Entity.archived_at.is_(None))).scalars().all()
    )

    def score(e: Entity) -> int:
        en = e.name.lower()
        s = 0
        if en == name_lc:
            s += 100
        elif name_lc in en or en in name_lc:
            s += 50
        else:
            overlap = {t for t in name_lc.split() if len(t) > 2} & {
                t for t in en.split() if len(t) > 2
            }
            s += 15 * len(overlap)
        if jurisdiction_code and e.jurisdiction_code == jurisdiction_code:
            s += 5
        return s

    best = max(entities, key=score, default=None)
    return best if (best and score(best) >= 15) else None


@router.post("/analyze", response_model=LicenseAnalyzeResponse)
def analyze_license_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> LicenseAnalyzeResponse:
    """Read an uploaded license PDF and return suggested form fields + a
    best-guess entity match. Nothing is persisted."""
    from compliance_agent.rule_extractor import (
        RuleExtractorUnavailable,
        extract_license_metadata,
        is_live,
    )

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")
    data = file.file.read()
    if len(data) > _MAX_EXTRACT_BYTES:
        return LicenseAnalyzeResponse(available=False, notes="File too large to read.")

    text = _extract_text_from_upload(file.filename, data)
    if len(text.strip()) < 120:
        return LicenseAnalyzeResponse(
            available=False,
            notes=(
                "Couldn't read text from this file (a scanned image?). "
                "Fill the fields in manually."
            ),
        )
    if not is_live():
        return LicenseAnalyzeResponse(
            available=False,
            notes="AI reading is off in this deployment. Fill the fields manually.",
        )

    try:
        meta = extract_license_metadata(text[:_MAX_PROMPT_CHARS])
    except RuleExtractorUnavailable as exc:
        return LicenseAnalyzeResponse(available=False, notes=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Claude call failed: {exc}") from exc

    code = (meta.jurisdiction_code or "").strip().lower() or None
    ent = _match_entity(db, entity_name=meta.entity_name, jurisdiction_code=code)
    log_activity(
        db,
        actor_id=user.id,
        action="license.ai_analyzed",
        target_type="license",
        payload={"matched_entity": ent.id if ent else None},
    )
    db.commit()
    return LicenseAnalyzeResponse(
        available=True,
        suggested_entity_id=ent.id if ent else None,
        entity_name=meta.entity_name,
        name=meta.name,
        license_type=meta.license_type,
        authority=meta.authority,
        jurisdiction_code=code or (ent.jurisdiction_code if ent else None),
        license_number=meta.license_number,
        issue_date=meta.issue_date,
        expiry_date=meta.expiry_date,
        notes=meta.notes,
    )


@router.post(
    "/{license_id}/ai-extract", response_model=LicenseAIExtractResponse
)
def ai_extract_obligations(
    license_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> LicenseAIExtractResponse:
    """Read the license file, ask Claude what obligations the holder owes,
    return candidate rules for the admin to tick + create.

    Falls back gracefully when:
      - no file is attached → returns available=False with a hint
      - AI is off (no ANTHROPIC_API_KEY (or OPENROUTER_API_KEY) / COMPLIANCE_AGENT_LIVE) → available=False
      - the PDF has no extractable text → notes explain
    """
    from compliance_agent.rule_extractor import (
        discovery_debug_enabled,
        extract_rules_from_text,
        is_live,
        RuleExtractorUnavailable,
        summarize_discovery,
    )

    lic = db.get(License, license_id)
    if lic is None:
        raise HTTPException(status_code=404, detail="License not found.")

    if not is_live():
        return LicenseAIExtractResponse(
            available=False,
            license_id=license_id,
            jurisdiction_hint=lic.jurisdiction_code,
            notes=(
                "AI extraction is off in this deployment. Set "
                "COMPLIANCE_AGENT_LIVE=1 and ANTHROPIC_API_KEY (or OPENROUTER_API_KEY) in the server "
                "environment, then retry."
            ),
        )

    text = _read_license_text(lic)

    # If a file is attached but yields no readable text (scanned PDF / image),
    # don't fail — fall back to knowledge mode using the licence's metadata
    # (jurisdiction, authority, type, name) + the entity's activity profile, so
    # the admin still gets a list to review.
    from_document = len(text.strip()) >= 200
    # Shared instruction: the licensee is also an operating company, so the
    # extract must be a SUPERSET — the licence's own obligations PLUS the
    # standard finance/tax/accounting filings any company in the jurisdiction
    # owes. This keeps the AI extract (source of truth) broader than the
    # finance-only website view, rather than narrower.
    # (A) Ground the extract in the curated catalogue — give Claude the
    # standard filing names we already track for this jurisdiction so it (a)
    # reuses those EXACT names and (b) doesn't miss filings the website lists.
    catalogue = (
        db.execute(
            select(Rule).where(
                Rule.jurisdiction_code == lic.jurisdiction_code,
                Rule.status == RuleStatus.production,
            )
        )
        .scalars()
        .all()
    )
    catalogue_ref = ""
    if catalogue:
        names = sorted(
            {
                (r.form_name or r.name or "").strip()
                for r in catalogue
                if (r.form_name or r.name)
            }
        )
        catalogue_ref = (
            "\n\n--- STANDARD FILINGS WE ALREADY TRACK FOR THIS JURISDICTION ---\n"
            "Where an obligation you list corresponds to one of these, use the "
            "EXACT name below (do not paraphrase). Make sure every relevant one "
            "here appears in your output, and add any further obligations you "
            "know of as new items.\n"
            "GRANULARITY: keep a strict 1:1 correspondence with these filings — "
            "do NOT merge two of them into a single item, and do NOT split one "
            "filing into several. One obligation per distinct filing:\n"
            + "\n".join(f"- {n}" for n in names)
        )

    # Keep the filing NAME and the FORM CODE in separate fields so the UI can
    # show them in separate columns.
    naming_rule = (
        "\n\nNAMING: put the human FILING name (no form code) in `name` — e.g. "
        "'Corporate Tax Return', 'Annual Safeguarding Audit'. Put ONLY the "
        "official form code/number in `form_name` — e.g. 'CT600', 'FSA056', "
        "'GSTR-3B'. If a filing has no formal form code, leave `form_name` equal "
        "to the filing name. Never put the form code inside `name`."
    )

    exhaustive_rule = (
        "\n\nSCOPE — ASSUME EVERY ACTIVITY IS PRESENT and return the MAXIMAL set. "
        "Cover ALL functions — Finance/Tax, Legal/Corporate, Compliance/AML, and "
        "HR/Payroll — and ALL item types: periodic filings & returns, licenses, "
        "permits, registrations, ongoing compliance obligations, reporting "
        "requirements, and industry-specific regulations.\n"
        "BE EXHAUSTIVE — list EVERY item that could conceivably apply to an "
        "entity of this type in this jurisdiction, not just a handful: corporate "
        "/ income tax, VAT / GST / sales tax, annual financial statements & "
        "audit, payroll & social-security / withholding, transfer pricing, "
        "economic substance, AML/CFT reports, UBO / beneficial-ownership "
        "registers, data-protection registrations, licence renewals, sector "
        "permits, statutory / registry filings, and any other recurring or "
        "event-based obligation. One entry per distinct item; do NOT merge or "
        "summarise. When unsure, INCLUDE it — narrowing happens later via the "
        "qualification questions. Do not pre-judge applicability here."
    )

    # Candidate universe is built REGULATOR-FIRST: an uploaded licence /
    # registration is the strongest evidence, so anchor on it before adding
    # generic company filings. Mirrors the discovery contract — assume
    # everything applies; the qualification questions narrow it later, never
    # here. (E.g. a FINTRAC MSB registration must pull in the full FINTRAC MSB
    # universe even if some items are later marked Conditional / Not Applicable.)
    universe_rule = (
        "\n\nBUILD THE CANDIDATE UNIVERSE IN THIS ORDER:\n"
        "1. Treat any uploaded licence / registration as the STRONGEST evidence. "
        "From it, identify the REGULATOR, the LICENSE TYPE, the REGISTRATION "
        "STATUS, and the AUTHORIZED ACTIVITIES, and use them to anchor the "
        "universe.\n"
        "2. FIRST generate the COMPLETE obligation universe tied to that "
        "regulator and license type — every reporting, renewal, AML/CFT and "
        "program-/independent-review obligation that regime imposes — before "
        "adding anything generic. The licence document is a FLOOR, not a "
        "ceiling: the regulator + license type + authorized activities are a "
        "POINTER to the full known regime — enumerate every obligation that "
        "regime imposes, including ones the document does not itself spell out, "
        "not just the ones written in the text. Example: a FINTRAC MSB "
        "registration pulls in ALL FINTRAC MSB reporting, renewal, AML/CFT and "
        "program-review obligations.\n"
        "3. THEN expand with the generic industry / company obligations. Nature "
        "of operations EXPANDS this universe — it never replaces or trims the "
        "regulator-specific obligations.\n"
        "4. Assume every primary qualification question is answered YES and do "
        "NOT filter here: include an obligation even if a later qualification "
        "question may mark it Conditional or Not Applicable."
    )

    finance_addendum = (
        f"\n\nAs a SECONDARY layer — AFTER the regulator-specific universe above "
        f"— also include the standard ongoing obligations any operating company "
        f"in {lic.jurisdiction_code.upper()} owes across every function, even "
        f"where they sit with a different authority than this licence's "
        f"regulator. These ADD TO, and never replace, the regulator-specific "
        f"obligations. Label each item's function/category accordingly "
        f"(Finance / Legal / Compliance / HR)."
    )

    # Discovery is deliberately answer-independent (assume all activities on) —
    # the qualification questions + Reassess do the narrowing. So we do NOT feed
    # the entity's answers into the discovery prompt.
    profile_block = ""
    # Nature of operations is a primary discovery input — what the entity does
    # drives which regulations could apply. It EXPANDS the regulator-specific
    # universe; it must never shrink it.
    _nature = getattr(lic.entity, "nature_of_operation", None) if lic.entity else None
    nature_block = (
        f"\n\nNATURE OF OPERATIONS (what this entity does): {_nature}. Use this "
        f"to ADD further obligations on top of the regulator-specific universe, "
        f"never to remove any." if _nature else ""
    )
    # Structured facts that anchor the baseline (corporate tax / audit / registry)
    # families: the licence type and the licensee's legal entity type. Stated as
    # plain facts — they only sharpen anchoring, they do not change discovery
    # breadth or posture.
    _legal_type = getattr(lic.entity, "legal_type", None) if lic.entity else None
    _lic_type = lic.license_type or None
    lic_type_line = f"\n\nLicense type: {_lic_type}." if _lic_type else ""
    legal_type_line = (
        f"\nLicensee's legal entity type: {_legal_type}." if _legal_type else ""
    )
    if from_document:
        # Document-grounded: read the actual license text.
        primer = (
            f"This is a regulator-issued license / authorisation document for "
            f"jurisdiction {lic.jurisdiction_code.upper()}, issued by "
            f"{lic.authority}. The license name is: {lic.name}. "
            f"Extract every ongoing compliance obligation the LICENSEE owes "
            f"as a result of HOLDING this license: filings, returns, fees, "
            f"reporting, periodic confirmations, change notifications, AML "
            f"obligations. Ignore one-off pre-licensing steps that have "
            f"already happened."
            f"{lic_type_line}{legal_type_line}"
            f"{universe_rule}"
            f"{exhaustive_rule}"
            f"{finance_addendum}"
            f"{nature_block}"
            f"{profile_block}"
            f"{naming_rule}"
            f"{catalogue_ref}"
            f"\n\n--- LICENSE TEXT BEGINS ---\n\n"
        )
        truncated = text[: max(0, _MAX_PROMPT_CHARS - len(primer))]
        payload_text = primer + truncated
    else:
        # No file attached — ask Claude from its regulatory knowledge so the
        # admin still gets a list to cross-check against the curated rules.
        payload_text = (
            f"No license document is available — work from your knowledge of "
            f"the regulator's regime.\n\n"
            f"Jurisdiction: {lic.jurisdiction_code.upper()}\n"
            f"Issuing authority / regulator: {lic.authority}\n"
            f"License name: {lic.name}\n"
            f"License type: {lic.license_type or '(not specified)'}\n"
            f"Licensee's legal entity type: {_legal_type or '(unknown)'}\n\n"
            f"List every ONGOING compliance obligation a holder of this kind of "
            f"license typically owes the regulator: periodic returns, filings, "
            f"fees, reports, periodic confirmations, change notifications, AML/"
            f"CFT obligations, renewals. For each, note whether it is mandatory "
            f"or conditional, and its usual frequency."
            f"{universe_rule}"
            f"{exhaustive_rule}"
            f"{finance_addendum}"
            f"{nature_block}"
            f"{profile_block}"
            f"{naming_rule}"
            f"{catalogue_ref}"
            f"\n\nIf you are unsure, mark applicability "
            f"accordingly rather than omitting it."
        )

    try:
        result = extract_rules_from_text(
            payload_text, jurisdiction_hint=lic.jurisdiction_code
        )
    except RuleExtractorUnavailable as exc:
        return LicenseAIExtractResponse(
            available=False,
            license_id=license_id,
            jurisdiction_hint=lic.jurisdiction_code,
            extracted_chars=len(text),
            notes=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"Claude call failed: {exc}"
        ) from exc

    log_activity(
        db,
        actor_id=user.id,
        action="license.ai_extracted",
        target_type="license",
        target_id=license_id,
        payload={
            "candidates": len(result.rules),
            "chars": len(text),
            "from_document": from_document,
        },
    )
    db.commit()

    extra_note = (
        None
        if from_document
        else (
            "No license PDF attached — this list is Claude's best estimate from "
            "the regulator + license type, not read from a document. Use it to "
            "cross-check your tracked filings; verify before creating rules."
        )
    )
    combined_notes = " ".join(n for n in (extra_note, result.notes) if n) or None

    # (B) Reconcile names against the catalogue. Where a candidate clearly
    # matches a filing we already track, adopt the catalogue's STANDARD name so
    # the extract and the website line up (and the cross-check matches cleanly).
    # `matched_standard` flags which ones were aligned vs genuinely new.
    def _match_catalogue(*texts: str) -> Optional[Rule]:
        cand = _tokens(*texts)
        if not cand:
            return None
        best, best_score = None, 0
        for r in catalogue:
            shared = cand & _tokens(r.form_name, r.name)
            if len(shared) > best_score:
                best, best_score = r, len(shared)
        # Need a couple of shared meaningful tokens to avoid false matches.
        return best if best_score >= 2 else None

    def _norm(s: object) -> str:
        return (getattr(s, "value", s) or "").strip().lower() if s else ""

    candidates: list[dict] = []
    for c in result.rules:
        # Finance-only: drop anything that isn't a Finance/Tax/Accounting
        # filing (legal, HR, governance, compliance, etc.). The exhaustive
        # prompt makes sure the finance set itself is complete.
        if not keep_function(
            getattr(c, "category", ""),
            getattr(c, "area", ""),
            getattr(c, "responsible_function", None),
        ):
            continue
        d = c.model_dump()
        match = _match_catalogue(d.get("form_name", "") or "", d.get("name", "") or "")
        if match is not None:
            # Standardise the filing NAME to the catalogue's so it lines up with
            # the website. Keep Claude's `form_name` (the form code) for the
            # separate Form column.
            std_name = match.name or match.form_name
            if std_name:
                d["name"] = std_name
            d["matched_standard"] = True
            # Surface the catalogue value + a *_differs flag where Claude diverges
            # from your currently-tracked rule, so you can see every difference
            # and decide which is right (the catalogue is NOT assumed correct).
            d["catalogue_due_date_rule"] = match.due_date_rule
            d["catalogue_frequency"] = match.frequency
            d["catalogue_applicability"] = (
                match.applicability.value if match.applicability else ""
            )
            d["due_date_differs"] = _norm(d.get("due_date_rule")) != _norm(
                match.due_date_rule
            )
            d["frequency_differs"] = _norm(d.get("frequency")) != _norm(
                match.frequency
            )
            d["applicability_differs"] = _norm(d.get("applicability")) != _norm(
                match.applicability
            )
        else:
            d["matched_standard"] = False
            d["due_date_differs"] = False
            d["frequency_differs"] = False
            d["applicability_differs"] = False
        candidates.append(d)

    # NOTE: the AI extract is the comprehensive "source of truth" / cross-check
    # tool, so it is deliberately NOT narrowed by the FINANCE_ONLY switch — it
    # surfaces every obligation Claude finds (finance + compliance + legal).
    # The FINANCE_ONLY filter only applies to the operational website lists
    # (applicable rules, catalogue, calendar), which stay a finance subset of
    # this full list. Filtering here too would leave licences like an FCA
    # Payment Institution (mostly compliance obligations) showing nothing.
    return LicenseAIExtractResponse(
        available=True,
        license_id=license_id,
        from_document=from_document,
        # Use the license's own short jurisdiction code (e.g. "uae"), NOT the
        # model's free-text inference (e.g. "United Arab Emirates"), so the
        # rules created from these candidates get a code that fits the column.
        jurisdiction_hint=lic.jurisdiction_code,
        extracted_chars=len(text),
        candidates=candidates,
        notes=combined_notes,
        debug_audit=summarize_discovery(result) if discovery_debug_enabled() else None,
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

    # 1. Candidate pool: approved (production) rules in this jurisdiction,
    #    across ALL functions (Finance / Legal / HR / Compliance) — this view
    #    is intentionally not narrowed by FINANCE_ONLY. _dedupe_rules collapses
    #    near-duplicate filings (e.g. two CT600 rows).
    pool = _dedupe_rules(
        [
            r
            for r in db.execute(
                select(Rule)
                .where(
                    Rule.entities.any(Entity.id == lic.entity_id),
                    # Mirror the Review & Assign "Approved" section exactly —
                    # that tab is status == production (no extra approved_at
                    # gate), so the license list shows the same approved set,
                    # but scoped to THIS licence's entity (not the whole
                    # jurisdiction) so unrelated entities' filings don't appear.
                    Rule.status == RuleStatus.production,
                )
                .order_by(Rule.category, Rule.form_name)
            )
            .scalars()
            .all()
            # All functions (Finance / Legal / HR / Compliance): this license
            # obligations view is intentionally NOT narrowed by FINANCE_ONLY.
        ]
    )

    license_tokens = _tokens(lic.authority, lic.license_type, lic.name)
    entity = lic.entity

    # 2. Tracking — for each rule, find the next upcoming, not-yet-completed
    # obligation against THIS license's entity. One query, then bucket by
    # rule_id.
    today_d = date.today()
    _fy = _parse_fy_end(getattr(entity, "fiscal_year_end", None))
    _ard = _parse_fy_end(getattr(entity, "annual_return_date", None))
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
            responsible_function=(
                rule.responsible_function
                or derive_function(rule.category, rule.area)
            ),
            plain_description=rule.plain_description,
            tax_type=(
                derive_tax_type(rule.name, rule.form_name, rule.category, rule.area)
                or (rule.tax_type.value if rule.tax_type else "Not a Tax")
            ),
            relevance=relevance,
            match_reason=match_reason,
            next_obligation_id=ob.id if ob else None,
            next_due_date=ob.due_date if ob else None,
            projected_due_date=_next_due_for_rule(rule, today_d, _fy, _ard),
            next_status=ob.status.value if ob and ob.status else None,
            next_assignee=assignee,
            days_to_next=((ob.due_date - today_d).days if ob else None),
        )

    direct: list[LicenseRuleHit] = []
    entity_other: list[LicenseRuleHit] = []

    # Every approved (production) filing in the entity's jurisdiction is
    # applicable to it — across ALL functions (Finance / Legal / HR /
    # Compliance), not just Finance. Token-matching the licence authority only
    # affects the "why" label, not whether the row is shown.
    juris_label = lic.jurisdiction_code.upper()
    for rule in pool:
        rule_tokens = _tokens(rule.authority, rule.category, rule.area)
        shared = license_tokens & rule_tokens
        direct.append(
            _hit(
                rule,
                relevance="direct",
                match_reason=(
                    f"matched on: {', '.join(sorted(shared))}"
                    if shared
                    else f"Approved filing in {juris_label}"
                ),
            )
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


# ---------------------------------------------------------------------------
# Schedule a rule against a license → creates one Obligation row
# ---------------------------------------------------------------------------
class ScheduleRulePayload(BaseModel):
    rule_id: int
    due_date: Optional[date] = None
    assignee_id: Optional[int] = None
    notes: Optional[str] = None


class ScheduleRuleResponse(BaseModel):
    obligation_id: int
    due_date: date
    assignee_id: Optional[int]


_MONTH_LOOKUP = {
    **{m.lower(): i for i, m in enumerate(calendar.month_name) if m},
    **{m.lower(): i for i, m in enumerate(calendar.month_abbr) if m},
}


def _clamp_day(year: int, month: int, day: int) -> date:
    """Build a date, clamping the day to the month's length (e.g. 31 → 30)."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(max(day, 1), last))


def _next_on_day_of_month(base: date, day: int) -> date:
    """Next occurrence of `day`-of-month on/after `base`."""
    cand = _clamp_day(base.year, base.month, day)
    if cand >= base:
        return cand
    ny, nm = (base.year + 1, 1) if base.month == 12 else (base.year, base.month + 1)
    return _clamp_day(ny, nm, day)


def _parse_fy_end(text: Optional[str]) -> Optional[tuple[int, int]]:
    """Parse an entity's fiscal_year_end string into (month, day). Handles
    '31-Dec', '31 Mar', 'Dec 31', 'March 31', '31/12'. None when unparseable."""
    if not text:
        return None
    low = text.strip().lower()
    m = re.match(r"^\s*(\d{1,2})\s*[/-]\s*(\d{1,2})\s*$", low)  # 31/12 or 31-12
    if m:
        day, mon = int(m.group(1)), int(m.group(2))
        if 1 <= mon <= 12 and 1 <= day <= 31:
            return (mon, day)
    mon = next((idx for tok, idx in _MONTH_LOOKUP.items() if tok in low), None)
    dm = re.search(r"(\d{1,2})", low)
    if mon and dm and 1 <= int(dm.group(1)) <= 31:
        return (mon, int(dm.group(1)))
    return None


_MONTH_ABBR = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def canonical_fye(text: Optional[str]) -> Optional[str]:
    """Normalise any fiscal-year-end input ('December', '31 December', '31/12',
    'dec', 'Dec 31', '31-Dec') to a short canonical 'DD-Mon' string (e.g.
    '31-Dec') that always fits the column and parses the same way every time.
    Case- and format-insensitive. Returns None when unparseable."""
    parsed = _parse_fy_end(text)
    if not parsed:
        return None
    mon, day = parsed
    return f"{day:02d}-{_MONTH_ABBR[mon - 1]}"


def _add_months(d: date, n: int) -> date:
    """d shifted by n calendar months, clamping the day to the target month."""
    total = d.year * 12 + (d.month - 1) + n
    y, m = divmod(total, 12)
    return _clamp_day(y, m + 1, d.day)


def _next_due_for_rule(
    rule: Rule,
    base: date,
    fy_end: Optional[tuple[int, int]] = None,
    ard_end: Optional[tuple[int, int]] = None,
) -> date:
    """Best-effort REAL statutory deadline, parsed from the rule's
    `due_date_rule` text, instead of a naive "today + interval". Handles the
    common shapes: "by the 25th of the following month", explicit calendar
    dates ("by 30 Jun", "31 Dec"), "Nth day of the Mth month after the period
    end", and "N months after the (financial) year end". Fiscal-relative rules
    anchor on the entity's fiscal year-end when known (`fy_end` = (month, day)),
    falling back to a calendar (Dec-31) year-end. Falls back to an interval only
    when nothing parseable is found."""
    # A structured Due-Date Builder spec, when present, is the source of truth —
    # the calendar gets exactly the date the builder's preview showed.
    spec = getattr(rule, "due_date_spec", None)
    if spec:
        from compliance_agent.due_date_spec import next_due_dates

        dates = next_due_dates(spec, base, fy_end, count=1, ard_end=ard_end)
        if dates:
            return dates[0]

    low = (rule.due_date_rule or "").lower()
    freq = (rule.frequency or "").lower()
    fy_month, fy_day = fy_end or (12, 31)

    # Monthly: anchor on the day-of-month it's due ("by the 25th of the
    # following month"), NOT today + 30 days.
    if "month" in freq:
        m = re.search(
            r"(\d{1,2})\s*(?:st|nd|rd|th)\s+of\s+(?:the\s+)?(?:following|next|subsequent)\s+month",
            low,
        ) or re.search(r"by\s+the\s+(\d{1,2})\s*(?:st|nd|rd|th)\b", low)
        if m:
            return _next_on_day_of_month(base, int(m.group(1)))
        return base + timedelta(days=30)

    # Explicit calendar date(s): "30 Jun", "Jun 30", "25 Jul / 25 Jan" → pick
    # the nearest future one. Used for annual / half-yearly / quarterly filings.
    cal: list[tuple[int, int]] = []
    for mo in re.finditer(
        r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*",
        low,
    ):
        mon = _MONTH_LOOKUP.get(mo.group(2))
        if mon:
            cal.append((mon, int(mo.group(1))))
    for mo in re.finditer(
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\b", low
    ):
        mon = _MONTH_LOOKUP.get(mo.group(1))
        if mon:
            cal.append((mon, int(mo.group(2))))
    if cal:
        cands = [
            _clamp_day(yr, mon, d)
            for mon, d in cal
            for yr in (base.year, base.year + 1)
        ]
        future = [c for c in cands if c >= base]
        if future:
            return min(future)

    # "15th day of the 6th month after the end of the tax period" — the Mth
    # month after the fiscal year-end, on day N.
    m = re.search(
        r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+day\s+of\s+the\s+(\d{1,2})\s*(?:st|nd|rd|th)?\s+month",
        low,
    )
    if m and 1 <= int(m.group(2)) <= 12:
        day, months_after = int(m.group(1)), int(m.group(2))
        cands = []
        for fy_year in (base.year - 1, base.year, base.year + 1):
            t = _add_months(_clamp_day(fy_year, fy_month, fy_day), months_after)
            cands.append(_clamp_day(t.year, t.month, day))
        future = [c for c in cands if c >= base]
        if future:
            return min(future)

    # "N months after the financial year end / accounting-period end / close"
    # (also covers "within N months of period end") — anchor on the FY end.
    m = re.search(r"(\d{1,2})\s+months?\b", low)
    if m and re.search(
        r"year[\s-]*end|fiscal|financial|accounting period|tax period|"
        r"period[\s-]*end|reporting period|after the end|of the year|close",
        low,
    ):
        n = int(m.group(1))
        cands = [
            _add_months(_clamp_day(fy_year, fy_month, fy_day), n)
            for fy_year in (base.year - 1, base.year, base.year + 1)
        ]
        future = [c for c in cands if c >= base]
        if future:
            return min(future)

    # Nothing parseable — fall back to a sensible interval.
    if "quarter" in freq:
        return base + timedelta(days=90)
    if "half" in freq:
        return base + timedelta(days=180)
    if "annual" in freq or "year" in freq:
        return base + timedelta(days=365)
    return base + timedelta(days=60)


@router.post(
    "/{license_id}/schedule-rule",
    response_model=ScheduleRuleResponse,
    status_code=201,
)
def schedule_rule_for_license(
    license_id: int,
    payload: ScheduleRulePayload,
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> ScheduleRuleResponse:
    """Admin manually creates an obligation for a rule that applies to the
    license's entity. This is the production workflow — no auto-spawn — so
    admins only schedule what actually applies."""
    lic = db.get(License, license_id)
    if lic is None:
        raise HTTPException(status_code=404, detail="License not found.")

    rule = db.get(Rule, payload.rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")

    due = payload.due_date or _next_due_for_rule(
        rule, date.today(), _parse_fy_end(getattr(lic.entity, "fiscal_year_end", None)),
        _parse_fy_end(getattr(lic.entity, "annual_return_date", None))
    )

    # Refuse a duplicate scheduling (rule + entity + due + department).
    existing = db.execute(
        select(Obligation).where(
            Obligation.rule_id == rule.id,
            Obligation.entity_id == lic.entity_id,
            Obligation.due_date == due,
            Obligation.department == Department.compliance,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"An obligation for this rule already exists on {due}. "
                f"Pick a different date or open the existing one."
            ),
        )

    obligation = Obligation(
        rule_id=rule.id,
        entity_id=lic.entity_id,
        due_date=due,
        status=ObligationStatus.not_started,
        department=Department.compliance,
        assignee_id=payload.assignee_id,
        notes=payload.notes,
    )
    db.add(obligation)
    db.flush()

    log_activity(
        db,
        actor_id=actor.id,
        action="obligation.scheduled_from_license",
        target_type="obligation",
        target_id=obligation.id,
        payload={
            "license_id": license_id,
            "rule_id": rule.id,
            "due_date": str(due),
            "assignee_id": payload.assignee_id,
        },
    )
    db.commit()
    return ScheduleRuleResponse(
        obligation_id=obligation.id,
        due_date=obligation.due_date,
        assignee_id=obligation.assignee_id,
    )


# ---------------------------------------------------------------------------
# Schedule EVERY applicable filing for a license → fills the calendar at once
# ---------------------------------------------------------------------------
class ScheduleAllResponse(BaseModel):
    scheduled: int
    skipped_existing: int
    applicable: int


def _dept_for_rule(rule: Rule) -> Department:
    """Owning department for a rule, from its responsible function."""
    fn = (rule.responsible_function or derive_function(rule.category, rule.area) or "").lower()
    if fn == "finance":
        return Department.finance
    if fn == "legal":
        return Department.legal
    return Department.compliance


class ScheduleRulesPayload(BaseModel):
    rule_ids: list[int]


@router.post(
    "/{license_id}/schedule-rules",
    response_model=ScheduleAllResponse,
    status_code=201,
)
def schedule_rules_for_license(
    license_id: int,
    payload: ScheduleRulesPayload,
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> ScheduleAllResponse:
    """Schedule the SELECTED filings (the admin's filtered set) onto the
    calendar. Each obligation is routed to the department matching the rule's
    function (finance / compliance / legal). Skips duplicates."""
    lic = db.get(License, license_id)
    if lic is None:
        raise HTTPException(status_code=404, detail="License not found.")

    today_d = date.today()
    scheduled = skipped = 0
    # Every obligation starts on the generic "preparing" leg (compliance).
    # Who actually prepares it (Finance for VAT/tax, etc.) is shown by the
    # rule's function in the workflow + assign dropdown; the payment leg
    # (department -> finance) is set later by the admin hand-off.
    dept = Department.compliance
    for rid in payload.rule_ids:
        rule = db.get(Rule, rid)
        if rule is None:
            continue
        due = _next_due_for_rule(
            rule, today_d, _parse_fy_end(getattr(lic.entity, "fiscal_year_end", None)),
            _parse_fy_end(getattr(lic.entity, "annual_return_date", None))
        )
        existing = db.execute(
            select(Obligation).where(
                Obligation.rule_id == rule.id,
                Obligation.entity_id == lic.entity_id,
                Obligation.due_date == due,
                Obligation.department == dept,
            )
        ).scalar_one_or_none()
        if existing is not None:
            skipped += 1
            continue
        db.add(
            Obligation(
                rule_id=rule.id,
                entity_id=lic.entity_id,
                due_date=due,
                status=ObligationStatus.not_started,
                department=dept,
            )
        )
        scheduled += 1
    log_activity(
        db,
        actor_id=actor.id,
        action="license.scheduled_rules",
        target_type="license",
        target_id=license_id,
        payload={"scheduled": scheduled, "skipped_existing": skipped,
                 "requested": len(payload.rule_ids)},
    )
    db.commit()
    return ScheduleAllResponse(
        scheduled=scheduled,
        skipped_existing=skipped,
        applicable=len(payload.rule_ids),
    )


def _schedule_filings_for_license(
    db: Session, lic: License, *, mandatory_only: bool
) -> tuple[int, int, int]:
    """Create a compliance obligation for every approved (production) rule that
    belongs to THIS licence's entity. Scoped to the entity (not the whole
    jurisdiction) so one entity's approved filings never appear on another
    entity's licence, and a licence whose entity has no approved rules schedules
    nothing. Skips any that already have an obligation on the computed due date.
    Returns (scheduled, skipped_existing, applicable). Does NOT commit."""
    pool = _dedupe_rules(
        db.execute(
            select(Rule).where(
                Rule.entities.any(Entity.id == lic.entity_id),
                Rule.status == RuleStatus.production,
            )
        )
        .scalars()
        .all()
    )
    today_d = date.today()
    scheduled = skipped = applicable = 0
    for rule in pool:
        if mandatory_only and rule.applicability != Applicability.mandatory:
            continue
        applicable += 1
        due = _next_due_for_rule(
            rule, today_d, _parse_fy_end(getattr(lic.entity, "fiscal_year_end", None)),
            _parse_fy_end(getattr(lic.entity, "annual_return_date", None))
        )
        existing = db.execute(
            select(Obligation).where(
                Obligation.rule_id == rule.id,
                Obligation.entity_id == lic.entity_id,
                Obligation.due_date == due,
                Obligation.department == Department.compliance,
            )
        ).scalar_one_or_none()
        if existing is not None:
            skipped += 1
            continue
        db.add(
            Obligation(
                rule_id=rule.id,
                entity_id=lic.entity_id,
                license_id=lic.id,
                due_date=due,
                status=ObligationStatus.not_started,
                department=Department.compliance,
            )
        )
        scheduled += 1
    return scheduled, skipped, applicable


@router.post(
    "/{license_id}/schedule-all",
    response_model=ScheduleAllResponse,
    status_code=201,
)
def schedule_all_for_license(
    license_id: int,
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> ScheduleAllResponse:
    """Schedule an obligation for every applicable filing in this licence's
    jurisdiction, so all of them show up on the calendar in one go. Skips any
    filing that already has an obligation on the computed due date."""
    lic = db.get(License, license_id)
    if lic is None:
        raise HTTPException(status_code=404, detail="License not found.")

    scheduled, skipped, applicable = _schedule_filings_for_license(
        db, lic, mandatory_only=False
    )
    # Only log when something actually landed — this endpoint is now called
    # automatically every time the licence is opened, so logging no-ops would
    # flood the activity feed.
    if scheduled:
        log_activity(
            db,
            actor_id=actor.id,
            action="license.scheduled_all",
            target_type="license",
            target_id=license_id,
            payload={
                "scheduled": scheduled,
                "skipped_existing": skipped,
                "applicable": applicable,
            },
        )
    db.commit()
    return ScheduleAllResponse(
        scheduled=scheduled, skipped_existing=skipped, applicable=applicable
    )


# ---------------------------------------------------------------------------
# Import entities + licences from the Vance Inc. org-chart data
# ---------------------------------------------------------------------------
class ImportOrgChartResult(BaseModel):
    created_entities: int
    backfilled_entities: int
    created_licenses: int
    skipped_licenses: int


@router.post("/import-org-chart", response_model=ImportOrgChartResult)
def import_org_chart(
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> ImportOrgChartResult:
    """Admin-only: idempotently create every entity + licence from the Vance
    Inc. legal-entity org chart. Existing entities/licences (matched by name /
    licence number) are skipped — only missing ones are added, and each is a
    fully-editable row. Shareholding is not imported."""
    from compliance_agent.data.org_chart import sync_org_chart

    summary = sync_org_chart()
    log_activity(
        db,
        actor_id=actor.id,
        action="licenses.import_org_chart",
        target_type="license",
        target_id=None,
        payload=summary,
    )
    db.commit()
    return ImportOrgChartResult(**summary)
