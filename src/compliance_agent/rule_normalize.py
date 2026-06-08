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


__all__ = [
    "canonical_code",
    "CatalogEntry",
    "JURISDICTION_CATALOG",
]
