"""Deterministic dedupe + conservative LLM adjudication for extracted rules.

The AI extractors (``rule_extractor.extract_rules_from_text``) emit *candidate*
obligations as free text. The same underlying filing routinely comes back under
several phrasings in a single run — "Corporate Tax Balance Payment" vs
"Corporate Income Tax Balance Payment", T1134 listed twice, T4 three times.
A name+frequency dedupe can't catch these because the strings genuinely differ.

This module implements the Normalize -> Adjudicate -> Emit pass described in the
dedupe spec, operating on the candidate list *before* anything is persisted:

  Normalize   assign a deterministic ``canonical_key`` ("CA::T1134") from a
              per-jurisdiction form-code catalog (or a real leading form code),
              then group-by key and merge coded duplicates. Classify each into
              an ``obligation_type`` so non-filings (AML training, ongoing
              monitoring, PEP determination) can be routed out of the filings
              register instead of polluting it.

  Adjudicate  a conservative LLM pass over the *uncoded* remainder only, which
              proposes merges of records that refer to the same obligation but
              share no form code. Applied in code (>= 0.85 confidence) so every
              merge is logged; never edits the register directly.

Guiding rule: a FALSE MERGE hides an obligation, which is strictly worse than a
duplicate. Every step here biases toward keeping an item over dropping it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# obligation_type / register taxonomy
# ---------------------------------------------------------------------------
# A recurring return/statement with a deadline (T4, T1134, GST/HST return).
PERIODIC_FILING = "periodic_filing"
# A tax/levy payment (CIT balance, instalments).
PAYMENT = "payment"
# One-time or renewal registration / licence.
REGISTRATION_OR_LICENCE = "registration_or_licence"
# Program control, no filing: AML training, ongoing monitoring, PEP determination.
ONGOING_CONTROL = "ongoing_control"
# Record retention obligations.
RECORDKEEPING = "recordkeeping"
# Notification/filing fired by an event, not a calendar.
EVENT_TRIGGERED = "event_triggered"

OBLIGATION_TYPES = {
    PERIODIC_FILING,
    PAYMENT,
    REGISTRATION_OR_LICENCE,
    ONGOING_CONTROL,
    RECORDKEEPING,
    EVENT_TRIGGERED,
}

# Register routing — the scope fix. Continuous program controls aren't deleted,
# they're routed to a register where they belong, off the filings calendar.
_FILINGS_TYPES = {PERIODIC_FILING, PAYMENT, EVENT_TRIGGERED}
FILINGS_REGISTER = "filings"
CONTROLS_REGISTER = "controls"


def register_for(obligation_type: Optional[str]) -> str:
    return FILINGS_REGISTER if obligation_type in _FILINGS_TYPES else CONTROLS_REGISTER


# ---------------------------------------------------------------------------
# Per-jurisdiction canonical obligations catalog
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CatalogEntry:
    """A known filing for a jurisdiction. ``code`` is the stable identity;
    ``aliases`` are lowercase phrases that map a free-text candidate onto it."""

    code: str
    official_name: str
    obligation_type: str
    default_frequency: str = "annual"
    aliases: tuple[str, ...] = ()


# Jurisdiction codes match the app's own short codes (see licenses.py):
# india / uk / us / uae / singapore / lithuania / canada / eu.
# The catalog is intentionally a *floor*, not a ceiling: coded items not listed
# here still get a canonical_key from their leading form code, and anything
# uncoded flows to the adjudication pass. CRA (canada) is the most fleshed-out
# because that's where the observed duplicate storm lives.
JURISDICTION_CATALOG: dict[str, list[CatalogEntry]] = {
    "canada": [
        CatalogEntry(
            "T2", "Corporation Income Tax Return", PERIODIC_FILING, "annual",
            ("t2 return", "corporation income tax return", "corporate income tax return",
             "corporation tax return"),
        ),
        CatalogEntry(
            "CIT-BALANCE", "Corporate Income Tax Balance Payment", PAYMENT, "annual",
            ("corporate income tax balance payment", "corporate tax balance payment",
             "corporation tax balance payment", "cit balance payment",
             "income tax balance payment", "tax balance due payment"),
        ),
        CatalogEntry(
            "CIT-INSTALMENT", "Corporate Income Tax Instalments", PAYMENT, "monthly",
            ("corporate income tax instalment", "corporate tax instalment",
             "corporation tax instalment", "monthly tax instalment",
             "quarterly tax instalment", "tax instalment payment"),
        ),
        CatalogEntry(
            "T4", "Statement of Remuneration Paid (T4)", PERIODIC_FILING, "annual",
            ("t4 slip", "t4 return", "statement of remuneration",
             "t4 information return"),
        ),
        CatalogEntry(
            "T4A", "Statement of Pension, Retirement, Annuity, and Other Income (T4A)",
            PERIODIC_FILING, "annual",
            ("t4a slip", "t4a return", "statement of pension"),
        ),
        CatalogEntry(
            "T1134", "Information Return Relating to Controlled and Non-Controlled Foreign Affiliates (T1134)",
            PERIODIC_FILING, "annual",
            ("foreign affiliate information return", "t1134 return",
             "controlled and non-controlled foreign affiliates",
             "foreign affiliate return"),
        ),
        CatalogEntry(
            "T1135", "Foreign Income Verification Statement (T1135)", PERIODIC_FILING, "annual",
            ("foreign income verification", "t1135 return",
             "specified foreign property"),
        ),
        CatalogEntry(
            "T106", "Information Return of Non-Arm's Length Transactions with Non-Residents (T106)",
            PERIODIC_FILING, "annual",
            ("non-arm's length transactions with non-residents",
             "non arm's length transactions", "t106 return",
             "transactions with non-residents"),
        ),
        CatalogEntry(
            "RC4649", "Country-by-Country Report (RC4649)", PERIODIC_FILING, "annual",
            ("country-by-country report", "country by country report",
             "cbc report", "cbcr"),
        ),
        CatalogEntry(
            "GST-HST-RETURN", "GST/HST Return", PERIODIC_FILING, "quarterly",
            ("gst/hst return", "gst hst return", "goods and services tax return",
             "harmonized sales tax return"),
        ),
    ],
    "uk": [
        CatalogEntry(
            "CT600", "Company Tax Return (CT600)", PERIODIC_FILING, "annual",
            ("company tax return", "corporation tax return"),
        ),
        CatalogEntry(
            "VAT-RETURN", "VAT Return", PERIODIC_FILING, "quarterly",
            ("vat return", "value added tax return"),
        ),
    ],
    "india": [
        CatalogEntry(
            "GSTR-3B", "GSTR-3B Summary Return", PERIODIC_FILING, "monthly",
            ("gstr-3b", "gstr 3b", "summary return"),
        ),
        CatalogEntry(
            "GSTR-1", "GSTR-1 Outward Supplies Return", PERIODIC_FILING, "monthly",
            ("gstr-1", "gstr 1", "outward supplies"),
        ),
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
    collapse two different filings — same rule licenses._rule_key uses."""
    codes = _form_codes(form_name or "")
    if not codes:
        return None
    lead = re.sub(r"^[^A-Za-z0-9]+", "", form_name or "")
    code = codes[0]
    if lead.upper().startswith(code.upper()):
        return code
    return None


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


# ---------------------------------------------------------------------------
# obligation_type classification (deterministic heuristic for uncoded items)
# ---------------------------------------------------------------------------
_CONTINUOUS_HINTS = (
    "training", "ongoing monitoring", "ongoing due diligence", "monitoring",
    "risk assessment", "pep", "politically exposed", "screening",
    "policies and procedures", "policy", "procedure", "governance",
    "fit and proper", "internal control", "third-party determination",
    "third party determination", "beneficial owner determination",
)
_RECORD_HINTS = ("record keeping", "recordkeeping", "record retention", "retention of records", "retain records")
_PAYMENT_HINTS = ("payment", "instalment", "installment", "remittance", "remit", "levy", "fee payable")
_REGISTRATION_HINTS = ("registration", "renewal", "licence", "license", "authorisation", "authorization", "enrol")
_EVENT_HINTS = ("notification", "notify", "breach", "incident report", "change notification", "report a", "upon ")


def classify_obligation_type(cand: dict[str, Any]) -> str:
    """Best-effort obligation_type from a candidate's text + frequency."""
    name = (cand.get("name") or "")
    area = (cand.get("area") or "")
    desc = (cand.get("plain_description") or "")
    hay = f"{name} {area} {desc}".lower()
    freq = (cand.get("frequency") or "").strip().lower()

    if freq in {"continuous", "ongoing"} or any(h in hay for h in _CONTINUOUS_HINTS):
        if any(h in hay for h in _RECORD_HINTS):
            return RECORDKEEPING
        return ONGOING_CONTROL
    if any(h in hay for h in _RECORD_HINTS):
        return RECORDKEEPING
    if any(h in hay for h in _REGISTRATION_HINTS):
        return REGISTRATION_OR_LICENCE
    # "balance payment" / "instalment" but NOT "return" -> a payment, not a filing.
    if any(h in hay for h in _PAYMENT_HINTS) and "return" not in hay:
        return PAYMENT
    if freq in {"event-based", "event based", "event-driven", "event_driven"} or any(
        h in hay for h in _EVENT_HINTS
    ):
        return EVENT_TRIGGERED
    return PERIODIC_FILING


# ---------------------------------------------------------------------------
# Step 1: assign canonical identity + obligation_type
# ---------------------------------------------------------------------------
def _match_catalog(jurisdiction: str, name: str, form_name: str) -> Optional[CatalogEntry]:
    entries = JURISDICTION_CATALOG.get((jurisdiction or "").strip().lower(), [])
    if not entries:
        return None
    text = f"{form_name} {name}"
    upper = text.upper()
    # Match the catalog entry's own code as a whole word. This handles short
    # CRA codes like T2/T4 that the generic 3-char form-code heuristic skips,
    # while \b stops "T4" matching inside "T4A".
    for e in entries:
        if re.search(rf"\b{re.escape(e.code.upper())}\b", upper):
            return e
    hay = text.lower()
    for e in entries:
        for alias in e.aliases:
            if alias in hay:
                return e
    return None


def _assign_identity(jurisdiction: str, cand: dict[str, Any]) -> None:
    name = cand.get("name") or ""
    form_name = cand.get("form_name") or ""
    juris = (jurisdiction or "xx").strip().lower() or "xx"
    prefix = juris.upper()

    entry = _match_catalog(juris, name, form_name)
    if entry is not None:
        cand["canonical_key"] = f"{prefix}::{entry.code}"
        cand["code_status"] = "coded"
        cand["obligation_type"] = entry.obligation_type
        cand["_catalog_official"] = entry.official_name
        cand["register"] = register_for(entry.obligation_type)
        return

    code = _leading_form_code(form_name)
    if code:
        cand["canonical_key"] = f"{prefix}::{code.upper()}"
        cand["code_status"] = "coded"
    else:
        cand["canonical_key"] = None
        cand["code_status"] = "uncoded"

    otype = cand.get("obligation_type") or classify_obligation_type(cand)
    cand["obligation_type"] = otype
    cand["register"] = register_for(otype)


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------
def _label(cand: dict[str, Any]) -> str:
    return (cand.get("name") or cand.get("form_name") or "").strip()


def _absorb(survivor: dict[str, Any], loser: dict[str, Any], *, reason: str, confidence: float) -> None:
    """Fold ``loser`` into ``survivor``: record provenance, union sources, keep
    the higher confidence. Never drops information silently."""
    merged_from = list(survivor.get("merged_from") or [])
    loser_label = _label(loser)
    if loser_label and loser_label not in merged_from:
        merged_from.append(loser_label)
    merged_from.extend(
        m for m in (loser.get("merged_from") or []) if m not in merged_from
    )
    survivor["merged_from"] = merged_from
    survivor["merge_reason"] = reason
    survivor["merge_confidence"] = max(
        float(survivor.get("merge_confidence") or 0.0), float(confidence)
    )

    s_sources = list(survivor.get("sources") or [])
    for src in loser.get("sources") or []:
        if src not in s_sources:
            s_sources.append(src)
    if s_sources:
        survivor["sources"] = s_sources

    if loser.get("confidence") is not None:
        survivor["confidence"] = max(
            float(survivor.get("confidence") or 0.0), float(loser["confidence"])
        )


def _merge_coded(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group-by canonical_key; keep one record per non-null key. This collapses
    the T1134/T4/CIT-balance phrasing duplicates deterministically."""
    survivors: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for c in cands:
        key = c.get("canonical_key")
        if not key:
            out.append(c)
            continue
        if key in survivors:
            _absorb(
                survivors[key], c,
                reason=f"Same canonical obligation {key}; merged duplicate phrasing.",
                confidence=1.0,
            )
        else:
            survivors[key] = c
            out.append(c)
    return out


def _merge_exact_uncoded(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Among uncoded records, merge ones whose normalised names are identical.
    Conservative — identical normalised names are unambiguously the same item.
    Coded records (with a canonical_key) are left untouched."""
    survivors: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for c in cands:
        if c.get("canonical_key"):
            out.append(c)
            continue
        nk = _norm_name(_label(c))
        if nk and nk in survivors:
            _absorb(
                survivors[nk], c,
                reason="Identical obligation name; merged duplicate.",
                confidence=1.0,
            )
        else:
            if nk:
                survivors[nk] = c
            out.append(c)
    return out


# ---------------------------------------------------------------------------
# Step 2: conservative LLM adjudication over the uncoded remainder
# ---------------------------------------------------------------------------
ADJUDICATOR_SYSTEM = """You are a compliance-obligations adjudicator. You are given a list of candidate
regulatory obligations for a single jurisdiction that the upstream extractor could
NOT map to a known form code. Your only job is to identify which of these refer to
the SAME underlying obligation and should be merged.

A compliance register is being built from your output. In this setting, a FALSE MERGE
(collapsing two distinct obligations into one) causes a MISSED obligation, which is far
worse than leaving a duplicate. Therefore: when in doubt, DO NOT merge.

Rules:
1. Only merge records that refer to the exact same underlying legal obligation,
   differing only in wording. Same form, same trigger, same authority.
2. NEVER merge records with different obligation_type. A filing and a payment for
   the same tax are DISTINCT obligations.
3. NEVER merge if it would combine genuinely different forms. Near-identical names are
   a trap: e.g. "T4" and "T4A" are different forms — do not merge. "Quarterly instalment"
   and "balance payment" are different obligations — do not merge.
4. If two records share a real form/obligation code in their text, propose that code as
   the canonical_key.
5. Output every input record. Unmerged records appear as singleton clusters.
6. Preserve all original display_labels in `members`.

Merge only at confidence >= 0.85. Below that, emit them as separate singleton clusters
and let a human decide. Singleton clusters have confidence 1.0."""


_ADJ_MIN_CONFIDENCE = 0.85


def _adjudication_model():
    """Build the structured-output schema lazily so this module imports without
    pydantic (the deterministic dedupe core has no such dependency)."""
    from pydantic import BaseModel, Field

    class AdjudicationCluster(BaseModel):
        members: list[str] = Field(description="One or more input display_labels in this cluster.")
        canonical_key_proposal: Optional[str] = Field(
            default=None, description="Proposed JURIS::CODE key, or null."
        )
        merge_reason: str = Field(description="One sentence; for singletons: 'distinct obligation'.")
        confidence: float = Field(
            description="Confidence these are the SAME obligation (singletons = 1.0)."
        )

    class AdjudicationResult(BaseModel):
        clusters: list[AdjudicationCluster]

    return AdjudicationResult


def _adjudicate(
    jurisdiction: str,
    uncoded: list[dict[str, Any]],
    coded_context: list[dict[str, Any]],
    *,
    model: str,
):
    """Call the LLM to cluster uncoded candidates. Best-effort: returns None on
    any failure so the caller falls back to the deterministic result."""
    from compliance_agent.ai.llm_client import ai_available, make_client

    if not ai_available() or len(uncoded) < 2:
        return None

    payload = [
        {
            "display_label": _label(c),
            "obligation_type": c.get("obligation_type"),
            "frequency": c.get("frequency"),
        }
        for c in uncoded
    ]
    context = [
        {"canonical_key": c.get("canonical_key"), "display_label": _label(c)}
        for c in coded_context
        if c.get("canonical_key")
    ]
    import json

    user = (
        f"Jurisdiction: {(jurisdiction or 'XX').upper()}\n\n"
        f"Uncoded candidate obligations:\n{json.dumps(payload, indent=2)}\n\n"
        f"For context, here are already-coded obligations in this jurisdiction "
        f"(DO NOT merge into these unless the code clearly matches; they are shown "
        f"so you can recognise true duplicates):\n{json.dumps(context, indent=2)}"
    )

    try:
        client = make_client()
        response = client.messages.parse(
            model=model,
            max_tokens=8000,
            system=[{"type": "text", "text": ADJUDICATOR_SYSTEM}],
            messages=[{"role": "user", "content": user}],
            output_format=_adjudication_model(),
        )
    except Exception:  # noqa: BLE001 — never fail the extract over adjudication
        return None
    return response.parsed_output


def _apply_adjudication(
    uncoded: list[dict[str, Any]],
    result: Any,
    jurisdiction: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply clusters >= threshold in code. Returns (kept, dropped) where dropped
    were absorbed into a survivor. Labels not found map to nothing (skipped)."""
    by_label: dict[str, dict[str, Any]] = {}
    for c in uncoded:
        by_label.setdefault(_label(c), c)

    absorbed: set[int] = set()
    prefix = (jurisdiction or "XX").upper()

    for cluster in result.clusters:
        members = [by_label[m] for m in cluster.members if m in by_label]
        # de-dup member identity in case the model repeats a label
        seen_ids: set[int] = set()
        members = [m for m in members if id(m) not in seen_ids and not seen_ids.add(id(m))]
        if len(members) < 2 or cluster.confidence < _ADJ_MIN_CONFIDENCE:
            continue
        survivor = members[0]
        if cluster.canonical_key_proposal:
            ck = cluster.canonical_key_proposal.strip()
            if "::" not in ck:
                ck = f"{prefix}::{ck}"
            survivor["canonical_key"] = ck
            survivor["code_status"] = "coded"
        for loser in members[1:]:
            _absorb(
                survivor, loser,
                reason=cluster.merge_reason or "Adjudicated as the same obligation.",
                confidence=cluster.confidence,
            )
            absorbed.add(id(loser))

    kept = [c for c in uncoded if id(c) not in absorbed]
    dropped = [c for c in uncoded if id(c) in absorbed]
    return kept, dropped


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
@dataclass
class DedupeReport:
    input_count: int = 0
    output_count: int = 0
    merged: list[tuple[str, list[str]]] = field(default_factory=list)  # (survivor, [absorbed])

    @property
    def removed(self) -> int:
        return self.input_count - self.output_count


def normalize_and_dedupe(
    candidates: list[dict[str, Any]],
    *,
    jurisdiction: str,
    model: str = "claude-opus-4-7",
    adjudicate: bool = True,
) -> tuple[list[dict[str, Any]], DedupeReport]:
    """Run Normalize -> Adjudicate on a candidate list. Mutates the dicts in
    place (adds canonical_key / code_status / obligation_type / register /
    merged_from / merge_reason / merge_confidence) and returns the surviving
    records plus a report. Order of survivors is preserved (first wins)."""
    report = DedupeReport(input_count=len(candidates))
    if not candidates:
        report.output_count = 0
        return [], report

    for c in candidates:
        _assign_identity(jurisdiction, c)

    merged = _merge_coded(candidates)
    merged = _merge_exact_uncoded(merged)

    if adjudicate:
        coded = [c for c in merged if c.get("canonical_key")]
        uncoded = [c for c in merged if not c.get("canonical_key")]
        adj = _adjudicate(jurisdiction, uncoded, coded, model=model)
        if adj is not None:
            _kept, dropped = _apply_adjudication(uncoded, adj, jurisdiction)
            if dropped:
                dropped_ids = {id(d) for d in dropped}
                merged = [c for c in merged if id(c) not in dropped_ids]

    for c in merged:
        if c.get("merged_from"):
            report.merged.append((_label(c), list(c["merged_from"])))

    report.output_count = len(merged)
    return merged, report


__all__ = [
    "normalize_and_dedupe",
    "classify_obligation_type",
    "register_for",
    "DedupeReport",
    "CatalogEntry",
    "JURISDICTION_CATALOG",
    "OBLIGATION_TYPES",
    "FILINGS_REGISTER",
    "CONTROLS_REGISTER",
]
