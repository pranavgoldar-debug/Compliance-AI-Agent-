"""LLM-backed extractor that turns raw regulatory text into candidate Rule rows.

Distinct from `ComplianceExtractor` (which extracts conceptual obligations
like "obtain valid consent"). This one is tuned for filings / returns /
periodic reports / event-based notifications — the things a compliance team
actually tracks on a calendar.
"""
from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel, Field

from compliance_agent.ai.llm_client import ai_available, make_client
from compliance_agent.db import Applicability, TaxType


SYSTEM_PROMPT = """You convert raw regulatory text into a list of recurring or event-based filing obligations.

For each obligation you extract:
- Use the official form/report name where one exists (GSTR-3B, Form 1120, CT600, SAR, etc.). If there is no formal form, name the deliverable concisely (e.g. "PSP authorization renewal" or "Breach notification to supervisory authority"). Use the plain name only — do NOT append jurisdiction codes/suffixes ("VAT_CA", "VAT (UK)", "Return — DIFC") and do NOT add parenthetical explanations or asides in the name ("AGM (not a filing, but a statutory meeting)"). Just the name ("AGM"); put any explanation in `plain_description`.
- The authority who receives it (RBI, FCA, FinCEN, MAS, CBUAE, etc.).
- The frequency the source describes (Monthly / Quarterly / Annual / Half-Yearly / Event-based / Continuous / One-time / Bi-annual).
- A `due_date_rule` describing exactly when it must be filed for a calendar-year company. Include the date or day-of-month/quarter. Cite the rule's section if visible.
- `payment_rule` (optional) — fee amounts, payable taxes, percentages, late-fee structure where the source mentions them. Leave null when there's no payment.
- `applicability` — Mandatory by default; Conditional or Sector-specific only when the source signals a trigger.
- `applicability_note` — when Conditional/Sector-specific, write a short note explaining what triggers it.
- `plain_description` — ALWAYS provide one plain-English sentence explaining what the filing is and who must do it, in language a non-specialist understands. No jargon or form codes.
- `tax_type` — classify the obligation:
    - "Direct Tax" when it is a tax levied on income, profits, gains or wealth (Corporate/Income Tax returns, TDS/withholding on income, advance tax, capital gains, dividend distribution tax, etc.).
    - "Indirect Tax" when it is a tax on goods, services or transactions that is collected and remitted on the authority's behalf (GST/HST, VAT, Sales/Use Tax, Excise, Customs/Import Duty).
    - "Not a Tax" for everything else — AML/CFT reports, data-protection filings, statutory/corporate returns, licensing renewals, regulatory confirmations, fees that are not taxes, etc.
  When unsure whether something is a tax at all, choose "Not a Tax".

Rules:
- Do not invent obligations that aren't supported by the source text.
- Split compound clauses into separate rules where they impose independent duties.
- If multiple sub-forms file on different dates (e.g. quarterly TDS forms), output one Rule per sub-form.
- Keep `name` short and human-readable (under 100 chars). The full form name goes in `form_name`.
- Choose `category` from this list when possible: Regulatory, AML / CFT, Corporate Tax, Information Returns, VAT, GST/HST, Sales/Use Tax, Excise Tax, Forex / Cross-Border, Corporate & Statutory, Payroll, Pensions, Social Security, Workers Compensation, Data Protection & Privacy, Cybersecurity, Consumer Protection, CIS, Statistics, EU Reporting, Accounting Control, Unclaimed Property.
- `area` is a short sub-area within the category (e.g. "Suspicious transaction reporting" within "AML / CFT").

If the document is too short, ambiguous, or doesn't describe filing obligations at all, return an empty list and explain in `notes`."""


class CandidateRule(BaseModel):
    name: str = Field(description="Short human-readable name for the obligation (≤100 chars).")
    plain_description: Optional[str] = Field(
        default=None,
        description=(
            "One plain-English sentence a non-expert can understand explaining "
            "what this filing is and who must do it. No jargon, no form codes — "
            "e.g. 'Quarterly sales-tax return reporting VAT collected and paid.'"
        ),
    )
    category: str
    area: str = Field(description="Sub-area within the category.")
    form_name: str
    authority: str
    frequency: str
    due_date_rule: str
    payment_rule: Optional[str] = None
    applicability: Applicability = Applicability.mandatory
    applicability_note: Optional[str] = None
    tax_type: TaxType = Field(
        default=TaxType.not_tax,
        description="Direct Tax / Indirect Tax / Not a Tax classification.",
    )


class RuleExtractionResult(BaseModel):
    jurisdiction_hint: Optional[str] = Field(
        default=None,
        description="If you can infer the country/jurisdiction from the source, name it here.",
    )
    rules: list[CandidateRule]
    notes: Optional[str] = Field(
        default=None,
        description="Caveats, ambiguities, or sections you skipped.",
    )


class RuleExtractorUnavailable(Exception):
    """Raised when Live mode is required but disabled."""


def is_live() -> bool:
    # Mirrors ai.ai_available — live mode + either backend's key.
    return ai_available()


def extract_rules_from_text(
    document_text: str,
    *,
    jurisdiction_hint: Optional[str] = None,
    model: str = "claude-opus-4-7",
) -> RuleExtractionResult:
    """Call Claude on the supplied text and return candidate Rule rows."""
    if not is_live():
        raise RuleExtractorUnavailable(
            "AI rule extraction requires COMPLIANCE_AGENT_LIVE=1 plus either "
            "ANTHROPIC_API_KEY or OPENROUTER_API_KEY."
        )

    client = make_client()

    user_content = document_text
    if jurisdiction_hint:
        user_content = (
            f"Jurisdiction hint: {jurisdiction_hint}\n\n---\n\n{document_text}"
        )

    response = client.messages.parse(
        model=model,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
        output_format=RuleExtractionResult,
    )

    if response.parsed_output is None:
        raise RuntimeError(
            f"Rule extraction failed — stop_reason={response.stop_reason}."
        )
    return response.parsed_output


# ---------------------------------------------------------------------------
# License metadata extraction — read a regulator's license/authorisation PDF
# and pull out the fields needed to pre-fill the "Add license" form.
# ---------------------------------------------------------------------------
LICENSE_META_PROMPT = """You read a regulator-issued license / authorisation document and extract its key metadata so a compliance team can file it.

Extract these fields (leave a field null if the document doesn't state it — never guess):
- `entity_name` — the legal entity the license is ISSUED TO (the licensee / company name), exactly as written.
- `name` — a short human title for the license (e.g. "FCA Authorisation", "MAS Major Payment Institution Licence", "CBUAE SVF Licence"). If a formal title exists, use it.
- `license_type` — the category/type of licence if distinct from the name (e.g. "EMI", "Major Payment Institution", "Trade License").
- `authority` — the issuing regulator (e.g. FCA, MAS, CBUAE, RBI, FinCEN, Bank of Lithuania).
- `jurisdiction_code` — the country, mapped to EXACTLY one of: india, uk, us, uae, singapore, lithuania, canada, eu. Use null if it's none of these.
- `license_number` — the licence / registration / reference number.
- `issue_date` — the date granted/issued, as ISO YYYY-MM-DD.
- `expiry_date` — the expiry / renewal-due date, as ISO YYYY-MM-DD. Null if the licence has no expiry.
- `notes` — one short line of anything important (conditions, scope) — optional.

Be precise. Only use what the document actually says."""


class LicenseMetadata(BaseModel):
    entity_name: Optional[str] = None
    name: Optional[str] = None
    license_type: Optional[str] = None
    authority: Optional[str] = None
    jurisdiction_code: Optional[str] = None
    license_number: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None


def extract_license_metadata(
    document_text: str,
    *,
    jurisdiction_hint: Optional[str] = None,
    model: str = "claude-opus-4-7",
) -> LicenseMetadata:
    """Call Claude on a license document and return its metadata fields."""
    if not is_live():
        raise RuleExtractorUnavailable(
            "AI license reading requires COMPLIANCE_AGENT_LIVE=1 and an API key."
        )

    client = make_client()
    user_content = document_text
    if jurisdiction_hint:
        user_content = f"Jurisdiction hint: {jurisdiction_hint}\n\n---\n\n{document_text}"

    response = client.messages.parse(
        model=model,
        max_tokens=4000,
        system=[{"type": "text", "text": LICENSE_META_PROMPT}],
        messages=[{"role": "user", "content": user_content}],
        output_format=LicenseMetadata,
    )
    if response.parsed_output is None:
        raise RuntimeError(
            f"License metadata extraction failed — stop_reason={response.stop_reason}."
        )
    return response.parsed_output
