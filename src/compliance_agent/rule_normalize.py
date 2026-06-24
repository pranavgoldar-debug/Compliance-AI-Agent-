"""Canonical-key identity for filings, used to dedupe across phrasings.

The discovery extractor emits the same underlying filing under several phrasings
in a single run — "Corporate Tax Balance Payment" vs "Corporate Income Tax
Balance Payment", T1134 listed twice, T4 three times. The name+cadence signature
in ``api.entities`` can't collapse these because the strings genuinely differ.

``canonical_code(name, form_name, jurisdiction)`` returns a stable identity
("CANADA::T1134") derived deterministically from a per-jurisdiction form-code
catalog, or from a real leading form code as a fallback. Feeding that key into
the existing dedupe signatures makes the collapse/reconcile machinery recognise
those duplicates while never merging genuinely different forms.

Guiding rule: a FALSE MERGE hides an obligation, which is strictly worse than a
duplicate. The catalog matches on a filing's own code (whole-word, so "T4"
never matches inside "T4A") or on curated alias phrases — never on loose
substrings. This module is intentionally dependency-free so it imports and
unit-tests without the web stack.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# obligation_type values — carried as catalog metadata so a later pass can route
# filings vs program-controls. Only the dedupe (canonical_code) is wired today.
PERIODIC_FILING = "periodic_filing"
PAYMENT = "payment"
REGISTRATION_OR_LICENCE = "registration_or_licence"
ONGOING_CONTROL = "ongoing_control"
RECORDKEEPING = "recordkeeping"
EVENT_TRIGGERED = "event_triggered"


# ---------------------------------------------------------------------------
# Per-jurisdiction canonical obligations catalog
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CatalogEntry:
    """A known filing. ``code`` is the stable identity; ``aliases`` are lowercase
    phrases that map a free-text candidate onto it."""

    code: str
    official_name: str
    obligation_type: str = PERIODIC_FILING
    aliases: tuple[str, ...] = ()


# Jurisdiction codes match the app's own short codes (india / uk / us / uae /
# singapore / lithuania / canada / eu). The catalog is a FLOOR, not a ceiling:
# coded items not listed here still get a key from their leading form code, and
# uncoded items keep the existing name-based dedupe. CRA (canada) is the most
# fleshed-out because that's where the observed duplicate storm lives.
JURISDICTION_CATALOG: dict[str, list[CatalogEntry]] = {
    "canada": [
        CatalogEntry(
            "T2", "Corporation Income Tax Return", PERIODIC_FILING,
            ("t2 return", "corporation income tax return", "corporate income tax return",
             "corporation tax return"),
        ),
        CatalogEntry(
            "CIT-BALANCE", "Corporate Income Tax Balance Payment", PAYMENT,
            ("corporate income tax balance payment", "corporate tax balance payment",
             "corporation tax balance payment", "cit balance payment",
             "income tax balance payment", "tax balance due payment"),
        ),
        CatalogEntry(
            "CIT-INSTALMENT", "Corporate Income Tax Instalments", PAYMENT,
            ("corporate income tax instalment", "corporate tax instalment",
             "corporation tax instalment", "monthly tax instalment",
             "quarterly tax instalment", "tax instalment payment"),
        ),
        CatalogEntry(
            "T4", "Statement of Remuneration Paid (T4)", PERIODIC_FILING,
            ("t4 slip", "t4 return", "statement of remuneration", "t4 information return"),
        ),
        CatalogEntry(
            "T4A", "Statement of Pension, Retirement, Annuity, and Other Income (T4A)",
            PERIODIC_FILING, ("t4a slip", "t4a return", "statement of pension"),
        ),
        CatalogEntry(
            "T1134", "Information Return Relating to Controlled and Non-Controlled Foreign Affiliates (T1134)",
            PERIODIC_FILING,
            ("foreign affiliate information return", "t1134 return",
             "controlled and non-controlled foreign affiliates", "foreign affiliate return"),
        ),
        CatalogEntry(
            "T1135", "Foreign Income Verification Statement (T1135)", PERIODIC_FILING,
            ("foreign income verification", "t1135 return", "specified foreign property"),
        ),
        CatalogEntry(
            "T106", "Information Return of Non-Arm's Length Transactions with Non-Residents (T106)",
            PERIODIC_FILING,
            ("non-arm's length transactions with non-residents", "non arm's length transactions",
             "t106 return", "transactions with non-residents"),
        ),
        CatalogEntry(
            "RC4649", "Country-by-Country Report (RC4649)", PERIODIC_FILING,
            ("country-by-country report", "country by country report", "cbc report", "cbcr"),
        ),
        CatalogEntry(
            "GST-HST-RETURN", "GST/HST Return", PERIODIC_FILING,
            ("gst/hst return", "gst hst return", "goods and services tax return",
             "harmonized sales tax return"),
        ),
    ],
    "uk": [
        CatalogEntry("CT600", "Company Tax Return (CT600)", PERIODIC_FILING,
                     ("company tax return", "corporation tax return")),
        # Monthly FCA safeguarding return — collapses the AI's name variants
        # ("REP027 (…)" vs plain "Safeguarding Return") onto one identity. The
        # annual safeguarding AUDIT report carries no REP027 code and no
        # "…return" alias, so it stays a separate filing (no false merge).
        CatalogEntry("REP027", "REP027 (Payment Services Directive safeguarding return)", PERIODIC_FILING,
                     ("safeguarding return", "monthly safeguarding return",
                      "payment services directive safeguarding return")),
        # Other coded FCA RegData returns — same purpose: collapse the AI's name
        # variants ("FSA056 …" vs "Capital Adequacy Return") onto one identity.
        # Aliases are filing-specific (no loose/shared phrases), so genuinely
        # different returns never merge.
        CatalogEntry("FSA056", "Capital Adequacy Return (FSA056)", PERIODIC_FILING,
                     ("capital adequacy return", "capital-adequacy return")),
        CatalogEntry("FIN073", "Baseline Financial Resilience Report (FIN073)", PERIODIC_FILING,
                     ("baseline financial resilience report", "financial resilience report")),
        CatalogEntry("REP-CRIM", "Annual Financial Crime Report (REP-CRIM)", PERIODIC_FILING,
                     ("annual financial crime report", "financial crime report")),
        CatalogEntry("REP002", "Annual Controllers Report (REP002)", PERIODIC_FILING,
                     ("annual controllers report", "controllers report")),
        CatalogEntry("REP001", "Annual Close Links Report (REP001)", PERIODIC_FILING,
                     ("annual close links report", "close links report", "close-links report")),
        CatalogEntry("REP017", "Payments Fraud Report (REP017)", PERIODIC_FILING,
                     ("payments fraud report", "payment fraud report")),
        CatalogEntry("REP018", "Operational and Security Risk Report (REP018)", PERIODIC_FILING,
                     ("operational and security risk report", "operational & security risk report")),
        CatalogEntry("DISP-1.10B", "Complaints Return (DISP 1.10B)", PERIODIC_FILING,
                     ("complaints return", "complaints data report")),
    ],
    "india": [
        CatalogEntry("GSTR-3B", "GSTR-3B Summary Return", PERIODIC_FILING,
                     ("gstr-3b", "gstr 3b", "summary return")),
        CatalogEntry("GSTR-1", "GSTR-1 Outward Supplies Return", PERIODIC_FILING,
                     ("gstr-1", "gstr 1", "outward supplies")),
    ],
}


# ---------------------------------------------------------------------------
# Form code extraction (mirrors licenses._form_code / the frontend)
# ---------------------------------------------------------------------------
_FORM_CODE_RE = re.compile(r"[A-Z0-9][A-Z0-9]*(?:[-/][A-Z0-9]+)*")


def _form_codes(text: str) -> list[str]:
    """Letter+digit tokens that look like official form codes (CT600, T1134,
    GSTR-3B, RC4649). Pure-alpha or pure-digit tokens are excluded."""
    if not text:
        return []
    out: list[str] = []
    for tok in _FORM_CODE_RE.findall(text):
        if (
            any(c.isdigit() for c in tok)
            and any(c.isalpha() for c in tok)
            and 3 <= len(tok) <= 14
            and tok not in out
        ):
            out.append(tok)
    return out


def _leading_form_code(form_name: str) -> Optional[str]:
    """A form code only counts as identity when it *leads* the form name
    ('T1134 …', 'CT600 — …'). A code merely mentioned in passing must not
    collapse two different filings — same rule api.licenses._rule_key uses."""
    codes = _form_codes(form_name or "")
    if not codes:
        return None
    lead = re.sub(r"^[^A-Za-z0-9]+", "", form_name or "")
    code = codes[0]
    return code if lead.upper().startswith(code.upper()) else None


def _match_catalog(jurisdiction: str, name: str, form_name: str) -> Optional[CatalogEntry]:
    entries = JURISDICTION_CATALOG.get((jurisdiction or "").strip().lower(), [])
    if not entries:
        return None
    text = f"{form_name} {name}"
    upper = text.upper()
    # Match the entry's own code as a whole word — handles short CRA codes like
    # T2/T4 that the 3-char form-code heuristic skips, while \b stops "T4"
    # matching inside "T4A".
    for e in entries:
        if re.search(rf"\b{re.escape(e.code.upper())}\b", upper):
            return e
    hay = text.lower()
    for e in entries:
        if any(alias in hay for alias in e.aliases):
            return e
    return None


def canonical_code(
    name: Optional[str],
    form_name: Optional[str],
    jurisdiction: Optional[str] = None,
) -> Optional[str]:
    """Stable identity key for a filing ("CANADA::T1134"), or None when the
    filing can't be confidently coded (those keep the name-based dedupe).

    Resolution order: per-jurisdiction catalog (code word or curated alias),
    then a real leading form code. Never synthesises a key from arbitrary text.
    """
    name = name or ""
    form_name = form_name or ""
    prefix = ((jurisdiction or "").strip().lower() or "xx").upper()

    entry = _match_catalog(jurisdiction or "", name, form_name)
    if entry is not None:
        return f"{prefix}::{entry.code}"

    code = _leading_form_code(form_name)
    if code:
        return f"{prefix}::{code.upper()}"
    return None


def canonical_name(
    name: Optional[str],
    form_name: Optional[str],
    jurisdiction: Optional[str] = None,
) -> Optional[str]:
    """The catalog's single official display name for a filing when it matches a
    known catalog entry, else None (uncoded filings keep their discovered name).
    Powers the admin 'Standardize names' action that renames existing rows to one
    canonical name per filing."""
    entry = _match_catalog(jurisdiction or "", name or "", form_name or "")
    return entry.official_name if entry is not None else None


# ---------------------------------------------------------------------------
# Acronym / spelling normalization (jurisdiction-agnostic)
# ---------------------------------------------------------------------------
# Acronym → full form. We expand the SHORT form to the LONG form (never the
# reverse), whole-word only, so an acronym and its spelled-out name end up
# sharing tokens — "PAYE RTI FPS", "PAYE Real Time Information Full Payment
# Submission" and "Full Payment Submission (FPS)" all normalize alike. This is
# ADDITIVE: an expansion only adds the words the long form already uses, so it
# can never merge two genuinely different filings (the false merge we guard
# against). High-signal finance/compliance acronyms only — no ambiguous words.
_ACRONYM_EXPANSIONS: dict[str, str] = {
    "fps": "full payment submission",
    "rti": "real time information",
    "eps": "employer payment summary",
    "vat": "value added tax",
    "gst": "goods and services tax",
    "hst": "harmonized sales tax",
    "aml": "anti money laundering",
    "cft": "counter terrorist financing",
    "ctf": "counter terrorist financing",
    "kyc": "know your customer",
    "cdd": "customer due diligence",
    "edd": "enhanced due diligence",
    "psc": "persons with significant control",
    "boi": "beneficial ownership information",
    "ubo": "ultimate beneficial owner",
    "ctr": "currency transaction report",
    "sar": "suspicious activity report",
    "str": "suspicious transaction report",
    "cmar": "client money and assets return",
    "fbar": "foreign bank account report",
    "ofac": "office of foreign assets control",
    "ofsi": "office of financial sanctions implementation",
    "ein": "employer identification number",
    "tin": "taxpayer identification number",
    "nic": "national insurance contributions",
    "ers": "employment related securities",
    "esr": "economic substance",
    "cbcr": "country by country report",
    "mtl": "money transmitter license",
    "wps": "wage protection system",
}

# Spelling / regional variants → one canonical token. SAFE: pure spelling, not
# meaning (so it never collapses semantically different words). We deliberately
# do NOT fold the verb family return/report/filing/submission/declaration here —
# that risks a false merge, so the AI dedupe pass judges those in context.
_TERM_CANON: dict[str, str] = {
    "licence": "license",
    "licences": "license",
    "programme": "program",
    "programmes": "program",
    "organisation": "organization",
    "organisations": "organization",
    "centre": "center",
    "instalment": "installment",
    "instalments": "installment",
}


def normalize_phrase(text: Optional[str]) -> str:
    """Lowercase a filing name and normalize it for matching: expand known
    acronyms to their full form and canonicalize spelling/regional variants,
    reducing to space-separated alphanumeric words. Used by the dedupe keys so
    acronym-vs-full-form and spelling variants collapse before token comparison.
    Additive/spelling-only — never collapses semantically different words."""
    s = re.sub(r"[^a-z0-9]+", " ", (text or "").lower())
    out: list[str] = []
    for w in s.split():
        w = _TERM_CANON.get(w, w)
        exp = _ACRONYM_EXPANSIONS.get(w)
        out.extend(exp.split() if exp else [w])
    return " ".join(out)


__all__ = [
    "canonical_code",
    "canonical_name",
    "normalize_phrase",
    "CatalogEntry",
    "JURISDICTION_CATALOG",
]
