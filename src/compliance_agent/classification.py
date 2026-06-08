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


# Conduct/prudential regulators whose filings are Compliance regardless of the
# entity's activity (the recipient wins — see owner_team_engine RULE 1).
_REGULATOR_TOKENS = (
    "fca", "dfsa", "fintrac", "central bank", "conduct authority",
    "monetary authority", "securities commission", "prudential authority",
    "financial conduct", "financial services authority", " regulator",
)


def owner_team_engine(
    name: str = "",
    authority: str = "",
    category: str = "",
    area: str = "",
    triggering_activity: str | None = None,
) -> str:
    """Deterministic owner-team classifier — always returns exactly one of
    Finance / Compliance / Legal / HR (the routing spec). Decides by WHAT the
    filing is about and WHO receives it, applying rules in order with the three
    tie-breakers, then an activity fallback. Used as the deterministic fallback
    when the model doesn't set owner_team, and as a reconciliation signal."""
    subj = f"{name} {category} {area}".lower()
    recipient = (authority or "").lower()
    is_regulator = any(tok.strip() in recipient for tok in _REGULATOR_TOKENS)

    # TIE-BREAKER B — client-money/safeguarding, or an auditor's report to a
    # regulator about regulated conduct -> Compliance (NOT Finance), even though
    # it is an "audit". Checked before the audited-financial-statements case.
    if (
        "client money" in subj
        or "client-money" in subj
        or "safeguarding" in subj
        or ("audit" in subj and is_regulator and "financial statement" not in subj)
    ):
        return "Compliance"
    # TIE-BREAKER A — audited financial statements filed to a REGISTRY -> Finance
    # (about the numbers), NOT Legal, even though the registry receives it.
    if "audited financial" in subj or "statutory account" in subj or (
        "financial statement" in subj
        and ("registr" in recipient or "companies house" in recipient)
    ):
        return "Finance"
    # TIE-BREAKER C — data protection (registration / fee / breach) -> Legal.
    if any(k in subj for k in ("data protection", "data-protection", "privacy", "gdpr", "pipeda")):
        return "Legal"

    # RULE 1 — submitted TO a conduct/prudential regulator, OR an AML/financial-
    # crime / prudential / supervision / controllers / change-in-control /
    # breach / money-services filing -> Compliance (recipient wins; check FIRST).
    if is_regulator or any(k in subj for k in (
        "aml", "cft", "financial crime", "prudential", "capital adequacy",
        "supervision fee", "controllers", "change in control", "change-in-control",
        "breach", "material change", "significant event", "money services",
        "suspicious transaction", "terrorist property", "large cash transaction",
        "electronic funds transfer", "virtual currency transaction",
    )):
        return "Compliance"
    # RULE 2 — tax or audited numbers -> Finance.
    if any(k in subj for k in (
        "corporate tax", "corporation tax", "income tax", "tax return", "vat",
        "gst", "hst", "withholding", "tds", "transfer pricing", "fdi",
        "statistical", " t2", "t106",
    )):
        return "Finance"
    # RULE 3 — employee-facing -> HR.
    if any(k in subj for k in (
        "form 16", "provident fund", "state insurance", "pension",
        "social security", "eosb", "dews", "record of employment", "p60",
        "p11d", " t4", "payroll",
    )):
        return "HR"
    # RULE 4 — registry / governance / ownership -> Legal.
    if any(k in subj for k in (
        "annual accounts", "annual return", "confirmation statement", "director",
        "trade licence", "trade license", "deposits return", "beneficial owner",
        "ubo", "psc", "ben-2", "registry", "registrar",
    )):
        return "Legal"
    # RULE 5 — fallback by triggering activity.
    return {
        "licensed_financial_activity": "Compliance",
        "holds_customer_funds": "Compliance",
        "sanctions_exposure": "Compliance",
        "vat_gst_registered": "Finance",
        "intra_group_transactions": "Finance",
        "takes_foreign_investment": "Finance",
        "employs_staff": "HR",
        "registered_company": "Legal",
        "has_owners_controllers": "Legal",
        "holds_personal_data": "Legal",
    }.get(triggering_activity or "", "Compliance")


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
