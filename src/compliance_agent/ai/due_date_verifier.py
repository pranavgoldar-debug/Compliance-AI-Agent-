"""On-demand due-date verification against the live regulator source.

The seed/discovery due dates are the model's best guess from training (and fall
back to today+interval when the rule text isn't parseable). This module checks a
filing's deadline against the ACTUAL source using Claude's web-search tool, and
returns the deadline with a citation (source URL + verbatim quote) + confidence.

It is Anthropic-only — the OpenRouter/Grok backend doesn't expose web search —
and strictly best-effort: it never raises into a request, returning
``available=False`` with a reason instead. It is read-only: it reports what it
found and does NOT mutate the rule. A human decides whether to apply it.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from compliance_agent.ai.llm_client import active_backend, ai_available, make_client


class DueDateVerification(BaseModel):
    available: bool
    verified: bool = False
    due_date_rule: Optional[str] = None  # the deadline in plain English, confirmed
    source_url: Optional[str] = None
    source_quote: Optional[str] = None  # verbatim sentence from the source
    confidence: Optional[str] = None  # high / medium / low
    summary: Optional[str] = None
    notes: Optional[str] = None


def verify_available() -> bool:
    """Source verification needs Claude's web-search tool — Anthropic only."""
    return ai_available() and active_backend() == "anthropic"


_SYSTEM = (
    "You are a compliance researcher. Using web search, find the OFFICIAL "
    "statutory filing deadline for the filing described below, from the "
    "regulator's own website or the primary legislation — NOT a blog, law-firm "
    "summary, or aggregator. Then call record_due_date with: the deadline in "
    "plain English, the exact source URL you relied on, a short VERBATIM quote "
    "from that page stating the deadline, and your confidence. Set verified=true "
    "ONLY when you have confirmed it from an authoritative (regulator / "
    "legislation) source; otherwise set verified=false and explain in summary. "
    "Do not invent a deadline."
)

_TOOL = {
    "name": "record_due_date",
    "description": "Record the verified filing deadline and its source.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verified": {
                "type": "boolean",
                "description": "True only if confirmed from an authoritative regulator/legislation source.",
            },
            "due_date_rule": {
                "type": ["string", "null"],
                "description": "Deadline in plain English, e.g. 'within 6 months of the financial year end'.",
            },
            "source_url": {"type": ["string", "null"]},
            "source_quote": {
                "type": ["string", "null"],
                "description": "Verbatim sentence from the source page stating the deadline.",
            },
            "confidence": {"type": ["string", "null"]},
            "summary": {"type": ["string", "null"]},
        },
        "required": ["verified"],
    },
}


def verify_due_date_from_source(
    *,
    form_name: str,
    authority: str,
    jurisdiction: str,
    frequency: Optional[str] = None,
    current_rule_text: Optional[str] = None,
    model: str = "claude-opus-4-8",
) -> DueDateVerification:
    """Look up + confirm the official deadline for one filing. Best-effort."""
    if not verify_available():
        return DueDateVerification(
            available=False,
            notes=(
                "Source verification needs Claude (Anthropic) web search; it's "
                "unavailable on the current backend (set ANTHROPIC_API_KEY and "
                "remove OPENROUTER_API_KEY, with COMPLIANCE_AGENT_LIVE=1)."
            ),
        )

    user = (
        f"Filing: {form_name}\n"
        f"Authority / regulator: {authority}\n"
        f"Jurisdiction: {jurisdiction}\n"
        f"Frequency: {frequency or '(unknown)'}\n"
        f"Current (unverified) deadline text: {current_rule_text or '(none)'}\n\n"
        "Find and confirm the official filing deadline from the regulator's own "
        "site or the primary legislation, then call record_due_date."
    )

    try:
        client = make_client()
        response = client.messages.create(
            model=model,
            max_tokens=3000,
            system=_SYSTEM,
            tools=[
                # Server-side web search (Anthropic) + the structured-output tool.
                {"type": "web_search_20250305", "name": "web_search", "max_uses": 5},
                _TOOL,
            ],
            messages=[{"role": "user", "content": user}],
        )
    except Exception as e:  # noqa: BLE001
        return DueDateVerification(
            available=False, notes=f"Claude web-search call failed: {e}"
        )

    blocks = getattr(response, "content", None) or []
    for block in blocks:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == "record_due_date"
        ):
            raw = getattr(block, "input", None) or {}
            return DueDateVerification(
                available=True,
                verified=bool(raw.get("verified")),
                due_date_rule=raw.get("due_date_rule"),
                source_url=raw.get("source_url"),
                source_quote=raw.get("source_quote"),
                confidence=raw.get("confidence"),
                summary=raw.get("summary"),
            )

    # Model researched but didn't call the tool — surface its prose so the
    # admin still gets something rather than an empty result.
    texts = [
        getattr(b, "text", "")
        for b in blocks
        if getattr(b, "type", None) == "text"
    ]
    return DueDateVerification(
        available=True,
        verified=False,
        notes=" ".join(t for t in texts if t) or "No verification was produced.",
    )


__all__ = ["DueDateVerification", "verify_available", "verify_due_date_from_source"]
