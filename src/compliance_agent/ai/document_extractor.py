"""Read an uploaded document and infer the filing fields it documents.

Flow:
  1. open the file from storage
  2. extract plain text (pypdf for .pdf; raw decode otherwise)
  3. send to Claude with a tight prompt → JSON suggestion
  4. return suggestions to the API layer, which surfaces them as an
     "Auto-fill" preview the user accepts or edits before saving.

We never auto-write the obligation. The user always confirms.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from compliance_agent.ai import ai_available


MAX_DOC_CHARS = 40_000  # cap input to keep token cost bounded


class DocumentExtractionSuggestion(BaseModel):
    filing_reference: Optional[str] = Field(
        None, description="ACK number / receipt / portal reference, if present."
    )
    payment_amount: Optional[str] = Field(
        None, description="Total amount paid (currency symbol + value if visible)."
    )
    payment_reference: Optional[str] = Field(
        None, description="UTR / transaction id, if present."
    )
    completed_at: Optional[date] = Field(
        None, description="Date the filing was submitted (ISO date)."
    )
    notes_suggestion: Optional[str] = Field(
        None, description="Optional 1-2 sentence summary the user can paste into Notes."
    )
    confidence: str = Field(
        "low",
        description="overall confidence: high / medium / low",
    )


class DocumentExtractionResult(BaseModel):
    available: bool
    excerpt: Optional[str] = None  # what we sent to the model (for transparency)
    suggestion: Optional[DocumentExtractionSuggestion] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------
def _extract_text(path: Path, content_type: Optional[str]) -> str:
    """Best-effort text extraction. PDF via pypdf; plain text decoded as utf-8.
    Returns the empty string if nothing useful comes out."""
    suffix = path.suffix.lower()
    if suffix == ".pdf" or (content_type or "").lower() == "application/pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            parts: list[str] = []
            for page in reader.pages:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:
                    continue
            return "\n".join(p.strip() for p in parts if p.strip())
        except Exception:
            return ""
    # Plain text / csv / json — decode as utf-8 with errors=ignore.
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Public entry — produces a DocumentExtractionResult
# ---------------------------------------------------------------------------
def extract(path: Path, content_type: Optional[str]) -> DocumentExtractionResult:
    if not ai_available():
        return DocumentExtractionResult(
            available=False,
            error="AI is off in this deployment. Set COMPLIANCE_AGENT_LIVE=1 and ANTHROPIC_API_KEY to enable.",
        )

    text = _extract_text(path, content_type)
    if not text or len(text.strip()) < 40:
        return DocumentExtractionResult(
            available=True,
            excerpt=None,
            error=(
                "Couldn't extract readable text from the document. "
                "This usually means it's a scanned image PDF — re-OCR it and re-upload, "
                "or fill the fields manually."
            ),
        )

    # Trim to keep token cost predictable.
    excerpt = text[:MAX_DOC_CHARS]

    try:
        suggestion = _call_claude(excerpt)
        return DocumentExtractionResult(
            available=True, excerpt=excerpt[:4000], suggestion=suggestion
        )
    except Exception as e:
        return DocumentExtractionResult(
            available=True,
            excerpt=excerpt[:4000],
            error=f"Claude call failed: {e}",
        )


# ---------------------------------------------------------------------------
# Claude call — strict JSON via tool-use
# ---------------------------------------------------------------------------
_SYSTEM = """\
You are an assistant for an internal compliance ops team. You will be given the
full plain-text contents of ONE filing-related document (e.g. a tax return
acknowledgement, a payment challan, a regulator portal receipt).

Your job is to extract the few fields the operator needs to record this filing:
- filing_reference: the portal acknowledgement / receipt number (NOT a generic
  transaction id; that goes in payment_reference)
- payment_amount: the total paid by the entity, including the currency symbol
  if visible. Output exactly as printed.
- payment_reference: the UTR / transaction id used to make the payment, if any
- completed_at: the date the filing was submitted (ISO date)
- notes_suggestion: a one or two sentence summary the human reviewer might paste
  into the internal notes field. Strictly factual, no interpretation.
- confidence: overall confidence in your extraction. high if multiple fields are
  obvious; medium if one or two are inferred; low if you had to guess.

If a field isn't clearly present in the document, leave it null. Don't invent.
Return ONLY the structured JSON via the provided tool.
"""


def _call_claude(text: str) -> DocumentExtractionSuggestion:
    from compliance_agent.ai.llm_client import make_client

    client = make_client()
    tool = {
        "name": "record_extraction",
        "description": "Record the extracted filing fields.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filing_reference": {"type": ["string", "null"]},
                "payment_amount": {"type": ["string", "null"]},
                "payment_reference": {"type": ["string", "null"]},
                "completed_at": {"type": ["string", "null"]},
                "notes_suggestion": {"type": ["string", "null"]},
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                },
            },
            "required": ["confidence"],
        },
    }

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=_SYSTEM,
        tools=[tool],
        tool_choice={"type": "tool", "name": "record_extraction"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Document text follows between the triple-tilde fences. "
                    "Extract the filing fields and call record_extraction.\n\n"
                    f"~~~\n{text}\n~~~"
                ),
            }
        ],
    )

    # Find the tool_use block.
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "record_extraction":
            raw = block.input or {}
            # Coerce completed_at to a date if Claude returned a string.
            raw = dict(raw)
            if raw.get("completed_at"):
                try:
                    from datetime import datetime as _dt

                    raw["completed_at"] = _dt.fromisoformat(raw["completed_at"]).date()
                except ValueError:
                    raw["completed_at"] = None
            return DocumentExtractionSuggestion(**raw)

    raise RuntimeError("Claude didn't call the tool — see response: " + json.dumps(response.model_dump()))
