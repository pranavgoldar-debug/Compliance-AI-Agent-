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
from compliance_agent.classification import FINANCE_ONLY, derive_function, keep_function
from compliance_agent.api._helpers import log_activity
from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.db import (
    Applicability,
    Department,
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


_MAX_EXTRACT_BYTES = 4_000_000   # ~4 MB of source text — enough for any single licence
_MAX_PROMPT_CHARS = 60_000        # rough char cap to keep Claude prompt manageable


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
        extract_rules_from_text,
        is_live,
        RuleExtractorUnavailable,
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
    has_file = bool(lic.storage_path)

    # A file is attached but we couldn't pull readable text — that's a scanned
    # PDF / image. Don't silently fall back to knowledge-mode; tell the admin.
    if has_file and len(text.strip()) < 200:
        return LicenseAIExtractResponse(
            available=False,
            license_id=license_id,
            jurisdiction_hint=lic.jurisdiction_code,
            extracted_chars=len(text),
            notes=(
                "Couldn't pull readable text from the uploaded file. If it's "
                "a scanned PDF, run it through OCR first. If it's an image, "
                "convert to PDF / paste the relevant text into Compliance "
                "Rules → Add from text instead."
            ),
        )

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

    finance_addendum = (
        f"\n\nIMPORTANT — also include the standard ongoing FINANCIAL, TAX and "
        f"ACCOUNTING obligations any operating company in "
        f"{lic.jurisdiction_code.upper()} owes, even though they sit with a "
        f"different authority than this licence's regulator: corporate / income "
        f"tax returns, VAT / GST / sales-tax returns, annual financial "
        f"statements and audit filing, payroll & social-security / withholding "
        f"returns, transfer pricing, and economic-substance filings where "
        f"applicable. The licensee IS such a company, so these apply. Label "
        f"their function/category as Finance/Tax accordingly."
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
            f"{finance_addendum}"
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
            f"License type: {lic.license_type or '(not specified)'}\n\n"
            f"List every ONGOING compliance obligation a holder of this kind of "
            f"license typically owes the regulator: periodic returns, filings, "
            f"fees, reports, periodic confirmations, change notifications, AML/"
            f"CFT obligations, renewals. For each, note whether it is mandatory "
            f"or conditional, and its usual frequency."
            f"{finance_addendum}"
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
        # FINANCE_ONLY switch: Claude's extract is also narrowed to Finance
        # filings now (compliance / legal dropped) — the broadened prompt makes
        # sure the finance/tax obligations are present, so this isn't empty.
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
    #    FINANCE_ONLY switch: keep only Finance-function rules. _dedupe_rules
    #    collapses near-duplicate filings (e.g. two CT600 rows).
    pool = _dedupe_rules(
        [
            r
            for r in db.execute(
                select(Rule)
                .where(
                    Rule.jurisdiction_code == lic.jurisdiction_code,
                    Rule.status == RuleStatus.production,
                )
                .order_by(Rule.category, Rule.form_name)
            )
            .scalars()
            .all()
            if keep_function(r.category, r.area, r.responsible_function)
        ]
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
            responsible_function=(
                rule.responsible_function
                or derive_function(rule.category, rule.area)
            ),
            plain_description=rule.plain_description,
            tax_type=rule.tax_type.value if rule.tax_type else "Not a Tax",
            relevance=relevance,
            match_reason=match_reason,
            next_obligation_id=ob.id if ob else None,
            next_due_date=ob.due_date if ob else None,
            projected_due_date=_next_due_for_rule(rule, today_d),
            next_status=ob.status.value if ob and ob.status else None,
            next_assignee=assignee,
            days_to_next=((ob.due_date - today_d).days if ob else None),
        )

    direct: list[LicenseRuleHit] = []
    entity_other: list[LicenseRuleHit] = []

    # License-specific: a rule is "directly applicable" when its authority /
    # type token-matches the licence (e.g. an FCA licence surfaces FCA rules).
    # In FINANCE_ONLY mode the pool is already just Finance filings (tax / VAT
    # / CT etc.) — those apply to the entity by virtue of operating in the
    # jurisdiction, not via this licence's authority — so surface them all
    # rather than showing an empty list when the authority doesn't match.
    juris_label = lic.jurisdiction_code.upper()
    for rule in pool:
        rule_tokens = _tokens(rule.authority, rule.category, rule.area)
        shared = license_tokens & rule_tokens
        if shared:
            direct.append(
                _hit(
                    rule,
                    relevance="direct",
                    match_reason=f"matched on: {', '.join(sorted(shared))}",
                )
            )
        elif FINANCE_ONLY:
            direct.append(
                _hit(
                    rule,
                    relevance="direct",
                    match_reason=f"Finance filing in {juris_label}",
                )
            )
        elif rule.id in entity_rule_ids:
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


def _next_due_for_rule(rule: Rule, base: date) -> date:
    """Pick a sensible default due date for a manually-scheduled obligation
    when the admin doesn't pass one. Keeps it close enough that the alert
    window will still fire."""
    freq = (rule.frequency or "").lower()
    if "monthly" in freq:
        return base + timedelta(days=30)
    if "quarterly" in freq:
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

    due = payload.due_date or _next_due_for_rule(rule, date.today())

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
        due = _next_due_for_rule(rule, today_d)
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
    """Create a compliance obligation for every production rule in the
    licence's jurisdiction (the whole country set is applicable). Skips any
    that already have an obligation on the computed due date. Returns
    (scheduled, skipped_existing, applicable). Does NOT commit."""
    pool = _dedupe_rules(
        [
            r
            for r in db.execute(
                select(Rule).where(
                    Rule.jurisdiction_code == lic.jurisdiction_code,
                    Rule.status == RuleStatus.production,
                )
            )
            .scalars()
            .all()
            if keep_function(r.category, r.area, r.responsible_function)
        ]
    )
    today_d = date.today()
    scheduled = skipped = applicable = 0
    for rule in pool:
        if mandatory_only and rule.applicability != Applicability.mandatory:
            continue
        applicable += 1
        due = _next_due_for_rule(rule, today_d)
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
