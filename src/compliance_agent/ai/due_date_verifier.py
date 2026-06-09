"""On-demand due-date verification against the live regulator source.

The seed/discovery due dates are the model's best guess from training (and fall
back to today+interval when the rule text isn't parseable). This module checks a
filing's deadline against the ACTUAL source using a web search, and returns the
deadline with a citation (source URL + verbatim quote) + confidence.

Works on either backend:
  - Anthropic (native key)  → Claude's built-in web_search tool.
  - OpenRouter (any model)  → OpenRouter's `web` search plugin, so it runs on
                              whatever OPENROUTER_MODEL is set to (a Claude
                              model, Grok, etc.).

Strictly best-effort: it never raises into a request, returning
``available=False`` with a reason instead. Read-only: it reports what it found
and does NOT mutate the rule.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

from pydantic import BaseModel

from compliance_agent.ai.llm_client import (
    active_backend,
    ai_available,
    make_client,
    resolve_model,
)


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
    """Verification works on either backend (Anthropic web_search tool, or the
    OpenRouter web plugin). Just needs live mode + a key."""
    return ai_available()


_SYSTEM = (
    "You are a compliance researcher. Using web search, find the OFFICIAL "
    "statutory filing deadline for the filing described below, from the "
    "regulator's own website or the primary legislation — NOT a blog, law-firm "
    "summary, or aggregator. Report the deadline in plain English, the exact "
    "source URL you relied on, a short VERBATIM quote from that page stating the "
    "deadline, and your confidence. Mark verified=true ONLY when you have "
    "confirmed it from an authoritative (regulator / legislation) source; "
    "otherwise verified=false and explain in summary. Do not invent a deadline."
)

# Anthropic structured-output tool.
_TOOL = {
    "name": "record_due_date",
    "description": "Record the verified filing deadline and its source.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verified": {"type": "boolean"},
            "due_date_rule": {"type": ["string", "null"]},
            "source_url": {"type": ["string", "null"]},
            "source_quote": {"type": ["string", "null"]},
            "confidence": {"type": ["string", "null"]},
            "summary": {"type": ["string", "null"]},
        },
        "required": ["verified"],
    },
}

# For the OpenRouter path we ask for a JSON object directly.
_JSON_INSTRUCTION = (
    "\n\nReturn ONLY a JSON object (no prose, no markdown) with exactly these "
    'keys: {"verified": bool, "due_date_rule": string|null, "source_url": '
    'string|null, "source_quote": string|null, "confidence": '
    '"high"|"medium"|"low"|null, "summary": string|null}.'
)


def _user_message(form_name, authority, jurisdiction, frequency, current_rule_text) -> str:
    return (
        f"Filing: {form_name}\n"
        f"Authority / regulator: {authority}\n"
        f"Jurisdiction: {jurisdiction}\n"
        f"Frequency: {frequency or '(unknown)'}\n"
        f"Current (unverified) deadline text: {current_rule_text or '(none)'}\n\n"
        "Find and confirm the official filing deadline from the regulator's own "
        "site or the primary legislation."
    )


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    # Strip ```json fences if present, then grab the first {...} block.
    cleaned = re.sub(r"```(?:json)?", "", text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except Exception:  # noqa: BLE001
        return None


def _from_raw(raw: dict) -> DueDateVerification:
    return DueDateVerification(
        available=True,
        verified=bool(raw.get("verified")),
        due_date_rule=raw.get("due_date_rule"),
        source_url=raw.get("source_url"),
        source_quote=raw.get("source_quote"),
        confidence=raw.get("confidence"),
        summary=raw.get("summary"),
    )


def _verify_anthropic(user: str, model: str) -> DueDateVerification:
    client = make_client()
    response = client.messages.create(
        model=model,
        max_tokens=3000,
        system=_SYSTEM,
        tools=[
            {"type": "web_search_20250305", "name": "web_search", "max_uses": 5},
            _TOOL,
        ],
        messages=[{"role": "user", "content": user}],
    )
    blocks = getattr(response, "content", None) or []
    for block in blocks:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == "record_due_date"
        ):
            return _from_raw(getattr(block, "input", None) or {})
    texts = [getattr(b, "text", "") for b in blocks if getattr(b, "type", None) == "text"]
    raw = _extract_json(" ".join(t for t in texts if t))
    if raw:
        return _from_raw(raw)
    return DueDateVerification(
        available=True, verified=False,
        notes=" ".join(t for t in texts if t) or "No verification was produced.",
    )


def _verify_openrouter(user: str) -> DueDateVerification:
    """Use OpenRouter's `web` search plugin with whatever OPENROUTER_MODEL is
    configured (a Claude model, Grok, etc.). Calls the OpenAI SDK directly so we
    can pass the plugin + ask for a JSON object."""
    from openai import OpenAI

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
        default_headers={"X-Title": "Aspora Compliance OS"},
    )
    completion = client.chat.completions.create(
        model=resolve_model("claude-opus-4-8"),
        max_tokens=2000,
        messages=[
            {"role": "system", "content": _SYSTEM + _JSON_INSTRUCTION},
            {"role": "user", "content": user},
        ],
        # OpenRouter server-side web search (Exa) — works with any model.
        extra_body={"plugins": [{"id": "web", "max_results": 5}]},
    )
    text = completion.choices[0].message.content or ""
    raw = _extract_json(text)
    if raw:
        return _from_raw(raw)
    return DueDateVerification(
        available=True, verified=False,
        notes=text or "No verification was produced.",
    )


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
                "Verification needs live AI — set COMPLIANCE_AGENT_LIVE=1 and an "
                "API key (OPENROUTER_API_KEY or ANTHROPIC_API_KEY)."
            ),
        )

    user = _user_message(form_name, authority, jurisdiction, frequency, current_rule_text)
    try:
        if active_backend() == "openrouter":
            return _verify_openrouter(user)
        return _verify_anthropic(user, model)
    except Exception as e:  # noqa: BLE001
        return DueDateVerification(
            available=False, notes=f"Web-search verification failed: {e}"
        )


__all__ = ["DueDateVerification", "verify_available", "verify_due_date_from_source"]
