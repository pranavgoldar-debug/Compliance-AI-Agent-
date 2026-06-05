"""Lightweight classifiers shared by the seed, API and AI extractor.

`derive_function` maps a rule's category/area to the responsible function
(Finance / Compliance / Legal). It's a sensible default — every rule is
editable afterwards — so we keep it keyword-based rather than calling an LLM.
"""
from __future__ import annotations

import os

# Single app-wide switch. When on, every surface (license obligations, AI
# extract, rules/filings catalog, calendar, dashboard) shows ONLY Finance-
# function obligations — Compliance / Legal / HR are hidden, not deleted.
# Default OFF: the adaptive assessment covers ALL functions & item types
# (filings, licenses, permits, registrations). Set COMPLIANCE_AGENT_FINANCE_ONLY=1
# to restrict back to finance only.
FINANCE_ONLY = os.getenv("COMPLIANCE_AGENT_FINANCE_ONLY", "0") == "1"

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


# --- Tax-type classification ------------------------------------------------
# A filing is exactly one of: a tax on income/profits/gains (Direct), a tax on
# goods/services/transactions collected on the authority's behalf (Indirect), or
# not a tax at all (admin / statutory / social-security / regulatory filings).
# The AI extractor sets `tax_type` per rule and was inconsistent across runs
# (the same form labelled differently); this derives it deterministically so the
# badge is identical for identical forms. Returns None when it can't tell — the
# caller then keeps whatever is stored.
#
# Checked in priority order. Markers are matched against name + form_name +
# category + area, all lowercased and space-padded.
_INDIRECT_TAX = (
    " vat", " gst", " hst", " pst", " qst", "sales tax", "sales/use", "use tax",
    "value added", "excise", "customs", "import duty", "indirect tax",
)
# Things that look tax-ish by keyword but are NOT a tax — checked before Direct
# so e.g. an "Employer Payment Summary" or "Pension contribution" isn't swept in.
_NOT_A_TAX = (
    # Payroll filings are employment/withholding submissions, not a tax type we
    # badge — keep the whole Payroll family uniform (no Direct/Indirect badge).
    "payroll",
    "employer payment summary", " eps ", "wage protection", " wps ",
    "pension", "social security", "gpssa", "gratuity", "provident",
    "audit", "annual accounts", "statutory account", "financial statement",
    "confirmation statement", "annual return", "beneficial owner", " ubo ",
    " psc ", "economic substance", " esr ", "data protection", "sanction",
    "incorporation", "share scheme", "share-based",
)
_DIRECT_TAX = (
    "corporate tax", "corporation tax", "income tax", "ct600", "advance tax",
    "capital gains", "dividend tax", "withholding", " tds ", " paye", " nic",
    " cis", "real time information", " rti", "full payment submission", " fps",
    "payroll tax", "employment tax", "transfer pricing", "self assessment",
)


def derive_tax_type(
    name: str = "", form_name: str = "", category: str = "", area: str = ""
) -> str | None:
    """Deterministic 'Direct Tax' / 'Indirect Tax' / 'Not a Tax' for a filing,
    or None when undecidable (caller keeps the stored value)."""
    hay = f" {name} {form_name} {category} {area} ".lower()
    for kw in _INDIRECT_TAX:
        if kw in hay:
            return "Indirect Tax"
    for kw in _NOT_A_TAX:
        if kw in hay:
            return "Not a Tax"
    for kw in _DIRECT_TAX:
        if kw in hay:
            return "Direct Tax"
    return None


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
