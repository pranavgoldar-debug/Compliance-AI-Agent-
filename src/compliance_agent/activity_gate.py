"""Deterministic Primary-Activity gating.

Maps a discovered filing (Rule) to the Primary Activity flag that gates it, and
decides — from an entity's saved `finance_profile` answers — whether that filing
APPLIES to the entity or is NOT APPLICABLE for it.

Single source of truth so the Compliance Rules view, the calendar, and any
other surface stay consistent. Keyword-based (like `classification.derive_
function`) — intentionally NOT an LLM call.

Semantics (per product decision):
  - gating activity answered "no" / "na"   -> not_applicable (shown, but flagged)
  - gating activity answered "yes"          -> applicable
  - "tbc" / "unsure" / unanswered           -> applicable (keep; uncertain)
  - filing maps to no known activity        -> applicable (can't gate -> keep)

A filing that matches several activities is APPLICABLE if any matched activity
is "yes" (a Yes wins); it is only NOT applicable when a matched activity is
"no"/"na" and none of its matches is "yes". Under-inclusion is the dangerous
failure, so the bias is to keep.
"""
from __future__ import annotations

from typing import Optional

APPLICABLE = "applicable"
NOT_APPLICABLE = "not_applicable"

# Answers that switch a family OFF.
_OFF = {"no", "na"}

# Activity flag id -> substrings that identify its filing family, matched against
# the rule's name / form_name / category / area (all lowercased). Keep these
# aligned with the Primary Activity flags in
# frontend/src/lib/financeGates.ts. Substrings padded with spaces guard against
# matching inside longer words (e.g. " nic" vs "technic").
ACTIVITY_MATCHERS: dict[str, tuple[str, ...]] = {
    "vat_gst_registered": (
        "vat", "gst", "sales tax", "sales/use", "value added", "indirect tax",
    ),
    "employs_staff": (
        "payroll", "paye", " nic", "wps", "wage protection", "pension",
        "social security", "gratuity", "gpssa", "employment tax", "p11d",
        "p60", "real time information", " rti", " eps",
    ),
    "intra_group_transactions": (
        "transfer pricing", "transfer-pricing", "cbcr", "country-by-country",
        "master file", "local file",
    ),
    "conducts_esr_relevant_activity": ("economic substance", " esr"),
    "audit_required": ("audit", "audited financial"),
    "grants_equity": (
        "share scheme", "share-based", "employee share",
        "employment related securities", " ers", "emi ", "stock option",
        "share plan", " rsu",
    ),
    "takes_foreign_investment": (
        "fdi", "foreign investment", "foreign direct", "inbound investment",
    ),
    "holds_personal_data": (
        "data protection", "data-protection", "gdpr", "privacy",
    ),
    "has_owners_controllers": (
        "beneficial owner", "ubo", "significant control", " psc", "controller",
    ),
    "sanctions_exposure": ("sanction", "frozen asset", "ofsi", "ofac"),
    "licensed_financial_activity": (
        "prudential", "conduct return", "regulatory return", "capital adequacy",
        "icara", "rmar", "reg data", "fsa0",
    ),
    "holds_customer_funds": (
        "safeguarding", "client money", "client-money", "client asset", "cass",
    ),
    "registered_company": (
        "corporate tax", "corporation tax", "income tax return",
        "annual accounts", "statutory accounts", "ct600",
        "confirmation statement", "annual return",
    ),
}


# The Primary Activity flag ids (the gate keys saved on the entity's
# finance_profile). Used to separate primary answers from the secondary
# follow-up answers (vat_frequency, ct_income_band, tp_threshold, …) when a
# surface should consider primary answers only.
PRIMARY_ACTIVITY_FLAGS: frozenset[str] = frozenset(ACTIVITY_MATCHERS)


def primary_only(profile: Optional[dict]) -> Optional[dict]:
    """Strip a finance_profile down to just the Primary Activity answers,
    dropping the secondary follow-up answers. Returns None when nothing is left."""
    if not profile:
        return None
    kept = {k: v for k, v in profile.items() if k in PRIMARY_ACTIVITY_FLAGS}
    return kept or None


def matched_activities(name: str, form_name: str, category: str, area: str) -> set[str]:
    """The Primary Activity flag ids whose filing family this rule belongs to."""
    hay = " ".join(t for t in (name, form_name, category, area) if t).lower()
    hay = f" {hay} "  # pad so leading/trailing space-guarded needles match edges
    return {act for act, needles in ACTIVITY_MATCHERS.items() if any(n in hay for n in needles)}


def entity_applicability(
    profile: Optional[dict],
    *,
    name: str = "",
    form_name: str = "",
    category: str = "",
    area: str = "",
) -> str:
    """Return ``APPLICABLE`` or ``NOT_APPLICABLE`` for a filing, given the
    entity's Primary Activity answers (its ``finance_profile``)."""
    if not profile:
        return APPLICABLE
    hits = matched_activities(name, form_name, category, area)
    if not hits:
        return APPLICABLE
    answers = [str(profile.get(a, "")).strip().lower() for a in hits]
    if any(v == "yes" for v in answers):
        return APPLICABLE
    if any(v in _OFF for v in answers):
        return NOT_APPLICABLE
    return APPLICABLE
