"""Lightweight classifiers shared by the seed, API and AI extractor.

`derive_function` maps a rule's category/area to the responsible function
(Finance / Compliance / Legal). It's a sensible default — every rule is
editable afterwards — so we keep it keyword-based rather than calling an LLM.
"""
from __future__ import annotations

import os

# Single app-wide switch. When on, every surface (license obligations, AI
# extract, rules/filings catalog, calendar, dashboard) shows ONLY Finance-
# function obligations — Compliance / Legal are hidden, not deleted. Flip the
# env var to "0" to bring the full set back.
FINANCE_ONLY = os.getenv("COMPLIANCE_AGENT_FINANCE_ONLY", "1") == "1"

# Checked in priority order: a match in an earlier bucket wins.
_COMPLIANCE = (
    "aml", "cft", "ctf", "financial regulation", "consumer protection",
    "data protection", "risk", "fraud", "regulatory reporting", "regdata",
    "economic substance", "statistics", "complaints", "sanction",
    "fitness", "conduct", "prudential", "reporting",
)
_FINANCE = (
    "tax", "vat", "gst", "hst", "pst", "qst", "excise", "payroll",
    "pension", "social security", "accounting", "information return",
    "unclaimed property", "duty", "customs", "withholding", "remittance",
    "intrastat",
)
_LEGAL = (
    "corporate law", "corporate record", "corporate & statutory",
    "statutory filing", "statutory account", "company registration",
    "registry", "registrar", "beneficial owner", "ubo", "psc",
    "licens", "incorporation", "governance", "confirmation statement",
    "annual return", "change notification", "premises",
)


def derive_function(category: str = "", area: str = "") -> str:
    """Best-effort Finance / Compliance / Legal classification."""
    text = f"{category} {area}".lower()
    for kw in _COMPLIANCE:
        if kw in text:
            return "Compliance"
    for kw in _FINANCE:
        if kw in text:
            return "Finance"
    for kw in _LEGAL:
        if kw in text:
            return "Legal"
    return "Compliance"


def is_finance(
    category: str = "", area: str = "", responsible_function: str | None = None
) -> bool:
    """True when this rule belongs to the Finance function (using its stored
    function if set, else the keyword classifier)."""
    fn = responsible_function or derive_function(category, area) or ""
    return fn.strip().lower() == "finance"


def keep_function(
    category: str = "", area: str = "", responsible_function: str | None = None
) -> bool:
    """Filter predicate for the FINANCE_ONLY switch. When the switch is off
    everything passes; when on, only Finance-function rules pass."""
    if not FINANCE_ONLY:
        return True
    return is_finance(category, area, responsible_function)
