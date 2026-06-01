"""Phase 7 AI assist endpoints.

  POST /api/ai/extract-from-document/{document_id}
      Reads the uploaded file from storage, extracts plain text, and asks
      Grok to suggest filing_reference / payment_* / completed_at /
      notes_suggestion. Caller (the UI) shows these as a preview before
      writing anything.

  POST /api/ai/second-opinion/{obligation_id}
      Reviewer-style verdict on a pending-review obligation.

  POST /api/ai/check-rule-changes/{rule_id}
      Fetch the rule's source_url, snapshot, diff against the last
      snapshot. Admin-only.

All three gracefully return {available: false} when AI is off, so the UI can
keep buttons enabled-but-non-fatal.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from compliance_agent import storage
from compliance_agent.ai.document_extractor import (
    DocumentExtractionResult,
    extract as extract_doc,
)
from compliance_agent.ai.regulation_watcher import CheckResult, check as check_rule_source
from compliance_agent.ai.second_opinion import SecondOpinionResult, review as review_obligation
from compliance_agent.api._helpers import log_activity
from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.db import Document, User, get_session
from compliance_agent.rate_limit import limiter


router = APIRouter(prefix="/api/ai", tags=["ai"])


# ---------------------------------------------------------------------------
# Document auto-extract
# ---------------------------------------------------------------------------
@router.post(
    "/extract-from-document/{document_id}",
    response_model=DocumentExtractionResult,
)
@limiter.limit("30/minute")
def extract_from_document(
    request: Request,
    document_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DocumentExtractionResult:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    data = storage.read_bytes(doc.storage_path)
    if not data:
        raise HTTPException(status_code=410, detail="Document file is missing.")

    # extract_doc works on a file path; write the DB blob to a short-lived
    # temp file so we don't have to change the extractor.
    import tempfile
    from pathlib import Path as _Path

    suffix = _Path(doc.filename or doc.storage_path or "").suffix or ""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = _Path(tmp.name)
    try:
        result = extract_doc(tmp_path, doc.content_type)
    finally:
        try:
            tmp_path.unlink()
        except Exception:  # noqa: BLE001
            pass

    if result.available and result.suggestion is not None:
        # Log only on success so audit doesn't get flooded with "AI off" entries.
        log_activity(
            db,
            actor_id=user.id,
            action="ai.document_extracted",
            target_type="document",
            target_id=document_id,
            payload={"confidence": result.suggestion.confidence},
        )
        db.commit()

    return result


# ---------------------------------------------------------------------------
# Second opinion
# ---------------------------------------------------------------------------
@router.post(
    "/second-opinion/{obligation_id}",
    response_model=SecondOpinionResult,
)
@limiter.limit("30/minute")
def second_opinion(
    request: Request,
    obligation_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SecondOpinionResult:
    result = review_obligation(db, obligation_id)
    if result.available and result.opinion is not None:
        log_activity(
            db,
            actor_id=user.id,
            action="ai.second_opinion",
            target_type="obligation",
            target_id=obligation_id,
            payload={
                "verdict": result.opinion.verdict,
                "confidence": result.opinion.confidence,
            },
        )
        db.commit()
    return result


# ---------------------------------------------------------------------------
# Regulation change watcher (admin)
# ---------------------------------------------------------------------------
@router.post(
    "/check-rule-changes/{rule_id}",
    response_model=CheckResult,
)
@limiter.limit("20/minute")
def check_rule_changes(
    request: Request,
    rule_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> CheckResult:
    result = check_rule_source(db, rule_id, actor=user)
    if result.changed or result.is_first_snapshot or result.error:
        log_activity(
            db,
            actor_id=user.id,
            action="ai.rule_source_checked",
            target_type="rule",
            target_id=rule_id,
            payload={
                "changed": result.changed,
                "first_snapshot": result.is_first_snapshot,
                "http_status": result.http_status,
                "error": result.error,
            },
        )
        db.commit()
    return result
