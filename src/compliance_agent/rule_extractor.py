"""LLM-backed extractor that turns raw regulatory text into candidate Rule rows.

Distinct from `ComplianceExtractor` (which extracts conceptual obligations
like "obtain valid consent"). This one is tuned for filings / returns /
periodic reports / event-based notifications — the things a compliance team
actually tracks on a calendar.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Literal, Optional

from pydantic import BaseModel, Field

from compliance_agent.ai.llm_client import ai_available, log_usage, make_client
from compliance_agent.db import Applicability, TaxType

logger = logging.getLogger(__name__)


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
- Do not invent obligations for regulators, regimes or activities the source does not establish. BUT once the source establishes a regulator / licence type / authorised activity, the COMPLETE known obligation set for that regime IS supported — enumerate it in full (see REGIME COMPLETENESS below); do not limit yourself to the obligations the text states verbatim.
- ANTI-HALLUCINATION (critical): only return an obligation you can attribute to a SPECIFIC, real, named filing/return/form/regulation for THIS jurisdiction and regulator. "Complete the regime" means real filings you can name — NEVER fabricate a plausible-sounding filing to fill a gap. If you are not sure a filing genuinely exists, either omit it or return it with confidence "Pending verification – official source check" and say so in `applicability`; do not assert it. It is better to omit a doubtful row than to invent one. Set `confidence` honestly per row — reserve "Confirmed – official source" for filings you can actually cite.
- Split compound clauses into separate rules where they impose independent duties.
- If multiple sub-forms file on different dates (e.g. quarterly TDS forms), output one Rule per sub-form.
- ONE entry per distinct filing — do NOT duplicate. Do not output the same filing more than once: not under two different cadences (a return is filed at a SINGLE cadence — pick the one that applies, don't emit both a monthly and a quarterly version of the same return); not under both a generic and a jurisdiction-specific name (e.g. a national workers'-comp filing AND its provincial-board equivalent); and do not split one remittance/return/report into synonymous entries (e.g. one payroll-deductions remittance, not separate "PD7A" and "CPP/EI/withholding" rows; one breach report to the privacy regulator, not several).
- CORPORATE TAX has THREE distinct obligations — emit each exactly once, and do not omit any: (a) the annual return, (b) periodic instalments, and (c) the final balance/settlement payment due after year-end. The balance payment is separate from both the return and the instalments.
- Emit FILINGS / returns / reports / registrations — not internal program duties. Ongoing housekeeping that is not itself submitted (maintaining policies, running transaction monitoring, retaining records, keeping a risk assessment current) should be folded into the relevant compliance-program obligation, not listed as many separate "Continuous" items.
- Keep `name` short and human-readable (under 100 chars). The full form name goes in `form_name`.
- Choose `category` from this list when possible: Regulatory, AML / CFT, Corporate Tax, Information Returns, VAT, GST/HST, Sales/Use Tax, Excise Tax, Forex / Cross-Border, Corporate & Statutory, Payroll, Pensions, Social Security, Workers Compensation, Data Protection & Privacy, Cybersecurity, Consumer Protection, CIS, Statistics, EU Reporting, Accounting Control, Unclaimed Property.
- `area` is a short sub-area within the category (e.g. "Suspicious transaction reporting" within "AML / CFT").
- COVER ALL OBLIGATION TYPES for each regime, not just periodic returns. Where the regime imposes them, explicitly include: periodic returns & reports; renewal obligations; regulatory & supervision fees; attestations & confirmations; change-in-control approvals AND notifications; material business-change notifications; beneficial-ownership UPDATE filings (not just the initial register); controller & significant-shareholder filings; breach & incident reporting; outsourcing & operational notifications; and any other regulator-specific event-driven obligation. These non-periodic, event-driven duties are the ones most often missed — list each as its own Rule (frequency "Event-based" where appropriate).

REGIME COMPLETENESS — expand, do not summarize. When the source establishes a regulator, a licence/registration type, or an authorised activity, treat it as a POINTER to the COMPLETE known obligation universe that regulator imposes on that licence type — the document is a FLOOR, not a ceiling. Use the licence text and authorised activities to EXPAND the list, never merely to restate what the document spells out. Once a regime is identified, keep enumerating its obligations until that regime's universe is complete; do NOT stop after the most prominent periodic filings. The goal is higher RECALL of genuinely relevant obligations WITHIN already-identified regimes — not speculative obligations for regulators or activities the source has not established.

CROSS-CUTTING REGULATORS — do not stop at the primary or licensing regulator. A regulated firm answers to SEVERAL authorities beyond the one that licenses it. After enumerating the licensing regulator's regime, also identify and enumerate the obligations of every OTHER authority that applies to a firm of this kind in this jurisdiction — where the jurisdiction has them: the sanctions / asset-freezing authority; the investment-screening / national-security body; the data-protection authority; the tax authority; the companies / business registry; the pensions authority; and any statistics / central-bank reporting body. These sit OUTSIDE the licensing regime and are the regulators most often missed — give each its own obligations.

For EACH obligation also provide (spec §3/§4):
- `condition` — a machine boolean-tree (see the field's allowed attribute names) that decides applicability. Use all_of/any_of/none_of and leaf clauses over ONLY those attribute names. Statutory audit is DERIVED — gate it on company_size_band/audit_exemption_ineligible, never invent an "is audit required?" attribute.
- `triggering_activity` — the single activity flag id that gates it (or 'NEEDS_NEW_FLAG' if none fit; explain the gating characteristic in applicability_note).
- `anchor` — what the deadline counts from (e.g. 'Financial year end').
- `confidence` — your honesty flag for this row.
Also fill `coverage_notes`: for each domain you considered, say whether you swept it fully (Confirmed), only listed the headline returns (Partial), or didn't research it (Pending research). This is REQUIRED — it tells the reviewer where to look. COMPLETENESS SWEEP: do not settle for the headline returns. Before you would mark any domain "Partial", first ADD the obligations that would make it "Confirmed" — the non-headline, less-prominent items (sub-forms, periodic confirmations/attestations, fees, renewals, event-driven notifications) as their own Rules — rather than stopping. Reserve "Partial" for a domain you genuinely cannot complete, and name exactly what is missing in the note.

OWNER-TEAM TAGGING — set `owner_team` to exactly one of: Finance, Compliance, Legal, HR.
Decide by WHAT THE FILING IS ABOUT and WHO RECEIVES IT — not by the entity's activity. The same activity can route to different teams depending on the filing. Apply these rules in order and stop at the first match:
RULE 1 — Submitted TO a financial conduct/prudential regulator (FCA, DFSA, central bank as conduct regulator), OR an AML/financial-crime return, prudential/capital return, regulator supervision fee, controllers report to the regulator, client-money/safeguarding report, money-services auditor's report, or a material-event/breach/change-in-control notification to the regulator -> Compliance. (Check FIRST — the recipient wins, even if the entity also employs staff / is a registered company.)
RULE 2 — Tax or audited numbers: corporate/income tax return, tax audit report, VAT/GST return, withholding/TDS INCLUDING TDS on salaries, transfer-pricing forms, FDI/central-bank statistical returns, or AUDITED FINANCIAL STATEMENTS filed to a company registry -> Finance.
RULE 3 — Employee-facing: employee tax certificate (Form 16), provident fund, state insurance, pension/social-security contribution, end-of-service / workplace-savings (EOSB/DEWS) -> HR.
RULE 4 — Corporate-registry / governance / ownership / data-protection: annual accounts, annual return / confirmation statement, director KYC, trade-licence renewal, deposits return, beneficial-ownership return filed to a REGISTRY (BEN-2, PSC, UBO), or a data-protection registration/fee/breach -> Legal.
RULE 5 — Fallback by triggering activity: licensed_financial_activity / holds_customer_funds / sanctions_exposure -> Compliance; vat_gst_registered / intra_group_transactions / takes_foreign_investment -> Finance; employs_staff -> HR; registered_company / has_owners_controllers / holds_personal_data -> Legal.
TIE-BREAKERS: (A) Audited financial statements filed to a company REGISTRY -> Finance (about the numbers), NOT Legal. (B) A client-money/safeguarding audit, or any auditor's report submitted TO A REGULATOR about regulated conduct -> Compliance, NOT Finance. (C) Data protection -> Legal. Decide by recipient + subject, not the word "audit".
Worked checks your output must match: "DFSA Annual AML Return"->Compliance; "TDS on salary (24Q)"->Finance; "Form 16 to employees"->HR; "Audited Financial Statements to the Registrar"->Finance; "Client Money Auditor's Report to DFSA"->Compliance; "BEN-2 beneficial owners to the registry"->Legal; "Change-in-control approval to the DFSA"->Compliance; "Data protection notification"->Legal.
If still genuinely ambiguous, pick the earliest matching rule (Compliance > Finance > HR > Legal) and flag it in `applicability`. Never invent a team outside the four.

If the document is too short, ambiguous, or doesn't describe filing obligations at all, return an empty list and explain in `notes`."""


# ---------------------------------------------------------------------------
# Discovery debug (TEMPORARY) — used to validate WHY obligations do/don't
# appear. Populated only when COMPLIANCE_AGENT_DISCOVERY_DEBUG=1 (the debug
# addendum is appended to the prompt then). Off by default; not shown in the
# production UI — the fields simply stay null on normal runs.
# ---------------------------------------------------------------------------
def discovery_debug_enabled() -> bool:
    """True when the temporary discovery-debug switch is on."""
    return os.environ.get("COMPLIANCE_AGENT_DISCOVERY_DEBUG") == "1"


DiscoverySource = Literal[
    "License / Registration",
    "Regulator",
    "Nature of Operations",
    "Jurisdiction",
    "Generic Compliance Knowledge",
]


class ObligationDebug(BaseModel):
    why_discovered: str = Field(
        default="", description="One line: why this obligation was discovered."
    )
    discovery_sources: list[str] = Field(
        default_factory=list,
        description=(
            "Which discovery source(s) produced this obligation — one or more of: "
            "'License / Registration', 'Regulator', 'Nature of Operations', "
            "'Jurisdiction', 'Generic Compliance Knowledge'."
        ),
    )
    confidence_score: Optional[float] = Field(
        default=None,
        description="0.0–1.0 confidence that this obligation truly applies.",
    )
    trigger_facts: list[str] = Field(
        default_factory=list,
        description=(
            "The concrete extracted facts that triggered it, e.g. "
            "'Regulator: FINTRAC', 'License Type: MSB', 'Activity: Money "
            "Transmission', 'Jurisdiction: Canada'."
        ),
    )


class DiscoveryAudit(BaseModel):
    """The facts the model keyed off when building the candidate universe."""

    regulator: Optional[str] = None
    license_type: Optional[str] = None
    registration_status: Optional[str] = None
    authorized_activities: list[str] = Field(default_factory=list)
    jurisdiction: Optional[str] = None
    legal_entity_type: Optional[str] = None


DISCOVERY_DEBUG_ADDENDUM = """

DISCOVERY DEBUG MODE (diagnostics only — do NOT change WHICH obligations you output, only annotate them):
For EVERY obligation, also fill `debug`:
- `why_discovered`: one line explaining why it surfaced.
- `discovery_sources`: one or more of EXACTLY these labels — "License / Registration", "Regulator", "Nature of Operations", "Jurisdiction", "Generic Compliance Knowledge".
- `confidence_score`: 0.0–1.0 that it truly applies.
- `trigger_facts`: the concrete facts you keyed off (e.g. "Regulator: FINTRAC", "License Type: MSB", "Activity: Money Transmission", "Jurisdiction: Canada").
Also fill the top-level `audit` with the facts you extracted: `regulator`, `license_type`, `registration_status`, `authorized_activities`, `jurisdiction`, `legal_entity_type`. Leave a field null if the source doesn't state it — never guess."""


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
    due_date_spec: Optional[dict] = Field(
        default=None,
        description=(
            "STRUCTURED schedule so the calendar can compute real dates — the "
            "free-text due_date_rule alone cannot be scheduled, so always fill "
            "this when the timing is determinable. Shape: {\"frequency\": "
            "annual|semiannual|quarterly|monthly|onetime|event|continuous, "
            "\"basis\": fixed|after_period, \"day\": 1-31, \"month\": 1-12 "
            "(fixed basis), \"offset\": int, \"unit\": months|days "
            "(after_period basis, anchored on the entity's fiscal year-end), "
            "\"date\": YYYY-MM-DD (onetime)}. Examples: 'within 6 months of FY "
            "end' -> {\"frequency\":\"annual\",\"basis\":\"after_period\","
            "\"offset\":6,\"unit\":\"months\"}; 'by 31 March each year' -> "
            "{\"frequency\":\"annual\",\"basis\":\"fixed\",\"day\":31,"
            "\"month\":3}; a monthly return due on the 20th -> "
            "{\"frequency\":\"monthly\",\"basis\":\"fixed\",\"day\":20}. Use "
            "\"event\" or \"continuous\" (no dates) for event-driven / ongoing "
            "filings. The frequency here MUST match the frequency field above."
        ),
    )
    payment_rule: Optional[str] = None
    applicability: Applicability = Applicability.mandatory
    applicability_note: Optional[str] = None
    tax_type: TaxType = Field(
        default=TaxType.not_tax,
        description="Direct Tax / Indirect Tax / Not a Tax classification.",
    )
    # Spec §3/§4 fields — used by the deterministic verdict engine + provenance.
    condition: Optional[dict] = Field(
        default=None,
        description=(
            "Machine boolean-tree over the entity's attributes (spec §4). "
            "Leaf {\"attr\":name,\"<op>\":value} with ops eq/neq/gte/lte/gt/lt/in; "
            "combinators all_of/any_of/none_of/always. Use ONLY these attribute "
            "names: registered_company, licensed_financial_activity, "
            "holds_customer_funds, employs_staff, grants_equity, "
            "takes_foreign_investment, intra_group_transactions, "
            "holds_personal_data, vat_gst_registered, has_owners_controllers, "
            "sanctions_exposure, conducts_esr_relevant_activity, audit_required, "
            "corporate_tax_threshold_met, group_consolidated_revenue_threshold_met, "
            "vat_return_frequency, company_size_band, audit_exemption_ineligible, "
            "esr_earns_income. Booleans true/false; vat_return_frequency in "
            "monthly/quarterly/annual; company_size_band in micro/small/medium/large."
        ),
    )
    triggering_activity: Optional[str] = Field(
        default=None,
        description="The single activity flag id that gates this, or 'NEEDS_NEW_FLAG'.",
    )
    anchor: Optional[str] = Field(
        default=None,
        description="What the deadline rule counts from, e.g. 'Financial year end'.",
    )
    confidence: Optional[str] = Field(
        default=None,
        description=(
            "One of: 'Confirmed – official source', 'Confirmed scope – entity "
            "check needed', 'Standard rule – verify applicability', 'Pending "
            "verification – official source check'."
        ),
    )
    owner_team: Optional[Literal["Finance", "Compliance", "Legal", "HR"]] = Field(
        default=None,
        description=(
            "Responsible team — Finance / Compliance / Legal / HR — decided by "
            "WHAT THE FILING IS ABOUT and WHO RECEIVES IT (see the owner-team "
            "rules in the system prompt). Exactly one of the four."
        ),
    )
    # Temporary discovery-debug annotation — populated only when the debug
    # addendum is active (COMPLIANCE_AGENT_DISCOVERY_DEBUG=1); null otherwise.
    debug: Optional[ObligationDebug] = Field(
        default=None,
        description=(
            "Diagnostics: why this obligation was discovered, its source(s), a "
            "confidence score, and the trigger facts. Debug mode only."
        ),
    )


class CoverageNote(BaseModel):
    domain: str = Field(description="e.g. 'DFSA conduct returns'")
    status: str = Field(description="Confirmed | Partial — headline returns only | Pending research")
    note: Optional[str] = None


class RuleExtractionResult(BaseModel):
    jurisdiction_hint: Optional[str] = Field(
        default=None,
        description="If you can infer the country/jurisdiction from the source, name it here.",
    )
    rules: list[CandidateRule]
    coverage_notes: list[CoverageNote] = Field(
        default_factory=list,
        description=(
            "Which domains were swept fully vs only skimmed (Confirmed / "
            "Partial / Pending research). NOT optional — a domain with a few "
            "rows is not proof of completeness."
        ),
    )
    notes: Optional[str] = Field(
        default=None,
        description="Caveats, ambiguities, or sections you skipped.",
    )
    # Temporary discovery-debug audit — populated only in debug mode; null otherwise.
    audit: Optional[DiscoveryAudit] = Field(
        default=None,
        description="Debug mode only: the facts the model keyed off when building the universe.",
    )


def summarize_discovery(result: "RuleExtractionResult") -> dict:
    """Build the discovery-audit summary (extracted facts + obligation counts by
    source) for debug logging / responses. Counts are NON-EXCLUSIVE tallies — an
    obligation attributed to two sources is counted under both."""
    counts = {
        "regulator_derived": 0,
        "license_derived": 0,
        "operations_derived": 0,
        "generic_derived": 0,
    }
    for r in result.rules:
        srcs = (r.debug.discovery_sources if r.debug else None) or []
        # Match case-insensitively — the model sometimes varies the casing
        # ('Nature Of Operations' vs 'Nature of Operations'); the field is a
        # lenient str so it never breaks parsing, and we bucket loosely here.
        low = {str(s).strip().lower() for s in srcs}
        if "regulator" in low:
            counts["regulator_derived"] += 1
        if "license / registration" in low or "licence / registration" in low:
            counts["license_derived"] += 1
        if "nature of operations" in low:
            counts["operations_derived"] += 1
        # Jurisdiction + general regulatory knowledge both roll up to "generic".
        if "jurisdiction" in low or "generic compliance knowledge" in low:
            counts["generic_derived"] += 1
    return {
        "extracted_facts": result.audit.model_dump() if result.audit else None,
        "obligation_counts": counts,
        "total_obligations": len(result.rules),
    }


class RuleExtractorUnavailable(Exception):
    """Raised when Live mode is required but disabled."""


def is_live() -> bool:
    # Mirrors ai.ai_available — live mode + either backend's key.
    return ai_available()


# Appended to the system prompt on a length-cut-off retry: keep the structured
# output compact so the full list fits the token budget without dropping items.
CONCISE_SUFFIX = (
    "\n\nOUTPUT BUDGET: keep the response COMPACT so the FULL list fits within "
    "the token limit. Make plain_description ONE short sentence, keep "
    "due_date_rule and applicability_note terse, and omit optional fields where "
    "not essential. Do NOT drop any obligations — just make each entry concise."
)


def _is_length_error(exc: Exception) -> bool:
    """True when an SDK call failed because the model hit its output limit
    (the response was truncated and couldn't be parsed)."""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    return (
        "length" in name
        or "length limit was reached" in msg
        or "max_tokens" in msg
        or "could not parse response content" in msg
    )


def _is_length_stop(stop_reason) -> bool:
    return str(stop_reason).lower() in ("max_tokens", "length")


def extract_rules_from_text(
    document_text: str,
    *,
    jurisdiction_hint: Optional[str] = None,
    model: str = "claude-opus-4-8",
    debug: Optional[bool] = None,
) -> RuleExtractionResult:
    """Call Claude on the supplied text and return candidate Rule rows.

    When `debug` is on (defaults to the COMPLIANCE_AGENT_DISCOVERY_DEBUG switch),
    the prompt also asks the model to annotate WHY each obligation was discovered
    and emit an extracted-facts audit, and we log a discovery summary."""
    if not is_live():
        raise RuleExtractorUnavailable(
            "AI rule extraction requires COMPLIANCE_AGENT_LIVE=1 plus either "
            "ANTHROPIC_API_KEY or OPENROUTER_API_KEY."
        )

    if debug is None:
        debug = discovery_debug_enabled()
    system_text = SYSTEM_PROMPT + (DISCOVERY_DEBUG_ADDENDUM if debug else "")

    client = make_client()

    user_content = document_text
    if jurisdiction_hint:
        user_content = (
            f"Jurisdiction hint: {jurisdiction_hint}\n\n---\n\n{document_text}"
        )

    # Generous output budget. If the model still runs out of room and the JSON
    # is truncated (a "length" cut-off → unparseable), retry ONCE with a compact
    # instruction so the full list fits without dropping obligations.
    response = None
    for concise in (False, True):
        sys_text = system_text + (CONCISE_SUFFIX if concise else "")
        try:
            response = client.messages.parse(
                model=model,
                max_tokens=32000,
                # Deterministic discovery: temperature 0 so the SAME entity
                # yields the SAME obligation set on every Refresh.
                temperature=0,
                system=[
                    {
                        "type": "text",
                        "text": sys_text,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_content}],
                output_format=RuleExtractionResult,
            )
        except Exception as exc:  # noqa: BLE001
            if not concise and _is_length_error(exc):
                continue  # truncated — retry compact
            raise
        log_usage(
            response,
            model=model,
            label="discovery (compact retry)" if concise else "discovery",
        )
        if (
            response.parsed_output is None
            and not concise
            and _is_length_stop(response.stop_reason)
        ):
            continue  # truncated — retry compact
        break

    if response is None or response.parsed_output is None:
        raise RuntimeError(
            "Rule extraction failed — the result exceeded the output budget "
            "even after a compact retry. Try narrowing the entity's scope or "
            "running discovery on fewer functions at a time."
        )
    result = response.parsed_output

    if debug:
        # Emit a server-log trace so discovery quality can be reviewed without
        # any production-UI surface. One audit line + one line per obligation.
        logger.info(
            "DISCOVERY DEBUG audit %s",
            json.dumps(summarize_discovery(result), default=str),
        )
        for r in result.rules:
            logger.info(
                "DISCOVERY DEBUG obligation %r -> %s",
                r.name,
                json.dumps(r.debug.model_dump(), default=str) if r.debug else "{}",
            )
    return result


# ---------------------------------------------------------------------------
# Gap-audit second pass — jurisdiction-agnostic completeness check. Replaces the
# need to hand-write a per-country recall block: after the main discovery pass,
# ask the model which WELL-KNOWN statutory finance/tax filings for this
# jurisdiction + legal type are MISSING from what was found, and feed them back
# through the same candidate->Rule path. Best-effort: never raises.
# ---------------------------------------------------------------------------
GAP_AUDIT_INSTRUCTIONS = (
    "COMPLETENESS REVIEW — an initial discovery pass has already run for the "
    "entity below. Your job is NARROW: name the WELL-KNOWN STATUTORY FINANCE / "
    "TAX filings for THIS jurisdiction and legal type that are MISSING from the "
    "ALREADY-FOUND list.\n"
    "- Return ONLY genuinely missing items. Do NOT repeat anything already in "
    "the ALREADY-FOUND list — match by form code or filing identity, ignoring "
    "wording, cadence and punctuation.\n"
    "- Scope is FINANCE / TAX only: corporate / income tax returns + their "
    "balance payment + instalments; indirect tax (VAT / GST / sales-tax) "
    "returns at EACH distinct cadence (list each return separately, never merge "
    "them); withholding / payroll tax returns; statutory financial statements / "
    "audit / accounts filings; transfer-pricing filings; and foreign-investment "
    "/ FX reporting of a financial character. Do NOT add pure HR, governance or "
    "legal items.\n"
    "- Name the OFFICIAL form / return and the authority for the jurisdiction. "
    "If unsure of the exact code, include it anyway with confidence 'Pending "
    "verification - official source check' rather than omitting it.\n"
    "- Be precise to the jurisdiction — never invent a filing that does not "
    "exist there. If nothing is missing, return an empty list.\n\n"
)


def audit_missing_filings(
    entity_context: str,
    found_filings: list[str],
    *,
    jurisdiction_hint: Optional[str] = None,
    model: str = "claude-opus-4-8",
) -> RuleExtractionResult:
    """Second-pass completeness check. Given the entity context and the filings
    the first pass already found, return candidate rows (same schema as
    extract_rules_from_text) for the well-known statutory finance/tax filings
    that are MISSING — so the caller creates them through the identical path.
    Jurisdiction-agnostic, so a new country needs no hand-written recall. Safe
    best-effort: returns an empty result (never raises) when the model is
    unavailable or the call fails."""
    if not is_live():
        return RuleExtractionResult(rules=[])

    found_block = "\n".join(f"- {f}" for f in found_filings if f) or "(none)"
    user_content = (
        GAP_AUDIT_INSTRUCTIONS
        + (f"Jurisdiction hint: {jurisdiction_hint}\n\n" if jurisdiction_hint else "")
        + entity_context
        + "\n\nALREADY-FOUND FILINGS (do NOT repeat these):\n"
        + found_block
    )

    client = make_client()
    try:
        response = client.messages.parse(
            model=model,
            max_tokens=16000,
            temperature=0,
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
    except Exception:  # noqa: BLE001
        logger.warning("gap-audit pass failed; skipping", exc_info=True)
        return RuleExtractionResult(rules=[])
    log_usage(response, model=model, label="gap-audit")
    return response.parsed_output or RuleExtractionResult(rules=[])


# ---------------------------------------------------------------------------
# Obligation assessment — given a company's profile answers + the discovered
# obligation list, decide which are mandatory / conditional / not-applicable.
# ---------------------------------------------------------------------------
ASSESS_PROMPT = """You are a compliance specialist. Given a SPECIFIC company's profile answers (primary + adaptive secondary) and a list of regulatory items that were discovered for it, decide for EACH item whether it is:
- "mandatory" — the company's answers make this clearly required.
- "conditional" — it may apply but a trigger/threshold is uncertain from the answers.
- "not_applicable" — the company's answers show this does NOT apply to it.

Decide ONLY from the provided answers and item details — do not invent facts.
For every item, copy its `form_name` EXACTLY as given, then provide:
- `verdict` — mandatory / conditional / not_applicable.
- `reason` — one line referencing the company's answers (e.g. "Not VAT-registered, so VAT return doesn't apply").
- `triggering_factors` — the specific answer(s)/fact(s) that drive this verdict (e.g. "Employs staff in UAE; pays via WPS"). Keep it short and concrete."""


class ObligationVerdict(BaseModel):
    form_name: str = Field(description="The obligation's form_name, copied EXACTLY.")
    verdict: str = Field(description="One of: mandatory, conditional, not_applicable")
    reason: str = Field(description="One-line reason referencing the company's answers.")
    triggering_factors: Optional[str] = Field(
        default=None,
        description="The specific answer(s)/fact(s) that drive this verdict.",
    )


class AssessmentResult(BaseModel):
    verdicts: list[ObligationVerdict]
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Adaptive secondary questions — generate jurisdiction/industry-specific
# follow-up questions for an entity from its nature of operations, licenses,
# jurisdiction, and the items already discovered.
# ---------------------------------------------------------------------------
QUESTION_GEN_PROMPT = """You build an ADAPTIVE follow-up questionnaire for ONE specific entity.

You are given, IN PRIORITY ORDER, the entity's uploaded licences/registrations (and their document text), the regulator that issued them, the activities those licences AUTHORISE, the entity's nature of operations, its known primary facts (already answered), and the list of regulatory items already discovered for it. Discovery deliberately assumed every activity is present, so the discovered list is broad ON PURPOSE.

PURPOSE — APPLICABILITY ONLY. Your questions exist solely to decide which ALREADY-DISCOVERED items are Mandatory, Conditional, Not Applicable, or exempt for THIS entity. They must NEVER be used to shrink, gate, or remove items from the discovered universe — discovery is the source of truth for WHAT could apply; you only validate applicability, conditionality and exemptions.

FACT HIERARCHY — resolve every fact from these sources IN ORDER, and ask ONLY about facts that remain genuinely uncertain after evaluating all six:
1. Uploaded licences / registrations (and their document text)
2. The regulator identified from those licences
3. The activities the licences AUTHORISE
4. Nature of operations
5. Known primary facts (already answered)
6. Generic assumptions

DO NOT ASK what is already established:
- If a licence/registration, the issuing regulator, the authorised activities, the nature of operations, or a known primary fact already establishes a fact, do NOT ask it.
- Never ask whether the entity holds a licence/registration it has already uploaded, and never ask the regulator to be identified — those are given.
- Never re-ask a primary question (the `primary_key` ids below) or any fact already present in the known primary facts.

ASK only what the documents cannot tell you — the high-impact facts only the entity can confirm:
- AUTHORISED vs PERFORMED: a licence lists what the entity MAY do, not what it actually DOES. When a licence authorises several activities, ask which ones the entity ACTUALLY performs — each performed activity gates its own obligations. E.g. when a licence authorises money-services activities, ask whether the entity actually performs each authorised activity (virtual-asset activity, money transmission, foreign-exchange dealing, ...) — do NOT ask whether it is a money-services business (the licence already confirms that).
- For a payment-services licence: ask whether customer funds are held / safeguarded, and whether cross-border payment services are provided — do NOT ask whether it provides payment services (the licence confirms it).
- For a financial-services licence: ask activity-specific operational questions — do NOT ask regulator-identification questions.
- Other applicability drivers only the entity knows: whether thresholds are met, registration/operating status (active vs dormant), employee headcount bands, tax-registration status, exemption eligibility, and filing frequencies.

DYNAMIC + JURISDICTION-SPECIFIC: the same primary question is global, but your follow-ups MUST vary by regulator, licence type, authorised activities, nature of operations, and jurisdiction. No generic boilerplate.

THRESHOLDS: when a question turns on a threshold/limit, STATE THE ACTUAL FIGURE for that jurisdiction in the question text or the option labels (e.g. "Are electronic funds transfers at or above the CAD 10,000 reporting threshold?", "Over the AED 375,000 corporate-tax threshold"). Never ask "above the threshold?" without naming the number. If there is NO clean regulatory threshold for a fact (employee headcount usually has none — payroll filings apply from the first employee, and remittance frequency is set by withholding amount, not headcount), do NOT invent arbitrary numeric bands — ask the decisive yes/no, or use the regime's REAL tiers (e.g. the actual remittance-frequency thresholds), never made-up buckets.

OPTION QUALITY — make the choices genuinely useful:
- Every option must be DECISION-RELEVANT: picking it must change at least one item's applicability. No filler options.
- For single-answer questions the options must be MUTUALLY EXCLUSIVE and cover the realistic answers; include a "Not applicable" or "Not sure" where it genuinely helps.
- Label options in concrete, real-world terms (named figures, named activities, named provinces/regimes) — not vague "low / medium / high".
- MULTI-SELECT: when the natural answer is "select all that apply" — e.g. which authorised activities the entity actually performs, which provinces it operates in, which customer types it serves — set `multi_select` true and list each choice as its own option. Use single-select (multi_select false) for yes/no, a single threshold band, or a single frequency.

`primary_key`: these PRIMARY activities are already asked separately —
  registered_company, licensed_financial_activity, holds_customer_funds,
  employs_staff, grants_equity, takes_foreign_investment,
  intra_group_transactions, holds_personal_data, vat_gst_registered,
  has_owners_controllers, sanctions_exposure, conducts_esr_relevant_activity,
  audit_required.
  If a question is a FOLLOW-UP to one of these (only relevant once that primary
  is "yes"), set `primary_key` to that id so it can be shown beneath it. If it
  is a general operation/nature-driven question not tied to a primary, leave
  `primary_key` null. Do NOT re-ask the primary questions themselves.

Every question MUST change the applicability of at least one already-discovered item and name that item/family in `drives`. Prefer closed answers (yes/no, real threshold bands, frequencies, named choices) over free text. Produce 4-10 questions. Each needs: a stable snake_case `key`, the `question` text, 2-6 `options` (each {value, label}), `multi_select` (true for "select all that apply", else false), `drives`, and `primary_key` (or null).
Return ONLY JSON matching the schema — no prose."""


class GenOption(BaseModel):
    value: str
    label: str


class GeneratedQuestion(BaseModel):
    key: str = Field(description="Stable snake_case id for the question.")
    question: str
    options: list[GenOption]
    multi_select: bool = Field(
        default=False,
        description="True when the answer is 'select all that apply' (checkboxes).",
    )
    drives: str = Field(default="", description="The item/family this question gates.")
    primary_key: Optional[str] = Field(
        default=None,
        description="The primary activity id this is a follow-up to, or null.",
    )


class GeneratedQuestions(BaseModel):
    questions: list[GeneratedQuestion]
    notes: Optional[str] = None


def generate_secondary_questions(
    context_block: str,
    *,
    model: str = "claude-opus-4-8",
) -> GeneratedQuestions:
    """Generate adaptive secondary qualification questions for an entity."""
    if not is_live():
        raise RuleExtractorUnavailable(
            "AI question generation requires COMPLIANCE_AGENT_LIVE=1 and an API key."
        )
    client = make_client()
    response = client.messages.parse(
        model=model,
        max_tokens=6000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=[
            {
                "type": "text",
                "text": QUESTION_GEN_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": context_block}],
        output_format=GeneratedQuestions,
    )
    log_usage(response, model=model, label="secondary questions")
    if response.parsed_output is None:
        raise RuntimeError(
            f"Question generation failed — stop_reason={response.stop_reason}."
        )
    return response.parsed_output


def assess_obligations(
    profile_block: str,
    obligations_block: str,
    *,
    jurisdiction_hint: Optional[str] = None,
    model: str = "claude-opus-4-8",
) -> AssessmentResult:
    """Classify each discovered obligation as mandatory / conditional /
    not_applicable for this company, based on its profile answers."""
    if not is_live():
        raise RuleExtractorUnavailable(
            "AI assessment requires COMPLIANCE_AGENT_LIVE=1 plus an API key."
        )
    client = make_client()
    user_content = (
        (f"Jurisdiction: {jurisdiction_hint}\n\n" if jurisdiction_hint else "")
        + profile_block
        + "\n\nOBLIGATIONS DISCOVERED:\n"
        + obligations_block
    )
    response = client.messages.parse(
        model=model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=[
            {
                "type": "text",
                "text": ASSESS_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
        output_format=AssessmentResult,
    )
    log_usage(response, model=model, label="obligation assessment")
    if response.parsed_output is None:
        raise RuntimeError(
            f"Assessment failed — stop_reason={response.stop_reason}."
        )
    return response.parsed_output


# ---------------------------------------------------------------------------
# Filing de-duplication — the discovery model (run repeatedly, and told to
# assume every activity) emits the SAME real-world filing several times under
# different names and authority spellings. Regex/token heuristics miss the
# semantic variants ("Federal Estimated Tax Instalments" == "Federal Corporate
# Tax Estimated Payments"; "IRS" == "Internal Revenue Service"), so we ask the
# model to cluster the genuine duplicates. CONSERVATIVE by design.
# ---------------------------------------------------------------------------
DEDUPE_PROMPT = """You de-duplicate and canonicalize a list of regulatory obligations for ONE company. The list was AI-generated and frequently contains the SAME real-world obligation written several times under different names, wordings, acronyms or authority spellings. Work JURISDICTION-AGNOSTICALLY (UK, US, EU, APAC, …) and judge by MEANING, not by title.

Decide whether two entries are the SAME obligation by comparing their SUBSTANCE, not their wording:
- the regulator / authority (allow spelling + acronym variants: "IRS" = "Internal Revenue Service", "OFAC" = "Office of Foreign Assets Control", "OFSI", "FinCEN", "FCA", "HMRC", "Companies House", "ICO", "MAS", "ASIC", "HKMA");
- the underlying legal requirement / governing rule;
- the filing purpose and the information reported;
- the trigger event and the frequency.
Normalize acronyms, abbreviations, full forms, synonyms, plural/singular and regional terms before comparing — treat "FPS" = "Full Payment Submission", "RTI" = "Real Time Information", "CTR" = "Currency Transaction Report", "SAR" = "Suspicious Activity Report", "CMAR" = "Client Money and Assets Return", "VAT" = "Value Added Tax", "Licence" = "License", "Controller Report" = "Controllers Report", and "Filing"/"Return"/"Submission"/"Report"/"Declaration" as interchangeable where the substance matches.

OUTPUT — two kinds of removal:
1) clusters: each names ONE entry to KEEP and the indices of OTHER entries that are the SAME obligation and should be removed. KEEP the clearest, most specific, correctly-spelled, canonical name.
2) redundant_parents: indices of GENERIC "parent" obligations to remove BECAUSE the list ALSO contains the SPECIFIC child obligations they summarise — so the inventory isn't double-counted. Only when the children are actually present.

Examples that ARE the same obligation (cluster + keep one):
- "Federal Estimated Tax Instalments", "Federal Estimated Tax Payments", "Federal Corporate Tax Estimated Payments" → one quarterly IRS estimated-tax payment.
- "PAYE Real Time Information Full Payment Submission", "PAYE RTI FPS", "Full Payment Submission (FPS)".
- "FCA Periodic Fee" and "FCA Periodic Fee and Tariff Data Return" (the same fee-tariff obligation) — keep the more complete name.
- "Annual Safeguarding Audit", "Safeguarding Audit Report", "Independent Safeguarding Audit".
- "Safeguarding Return (REP027)", "REP027 Safeguarding Return", "REP027 (Payment Services Directive safeguarding return)", "Monthly Safeguarding Return" — the MONTHLY safeguarding return (distinct from the annual audit above); keep the name "Safeguarding Return (REP027)".

Parent/child (put the GENERIC parent in redundant_parents, keep the specifics):
- Generic "State Money Transmitter License Renewal & Reporting" when specific "Michigan Money Transmitter License Renewal", "Maryland Money Transmitter License Renewal" are present.

Do NOT merge obligations that are genuinely DIFFERENT, even when related — when in doubt, KEEP them separate:
- Different states / jurisdictions (Maryland vs Michigan renewals are SEPARATE).
- Different forms that merely support one another (Form W-2 vs Form W-3; Form 941 vs Form 940; 1099 vs W-2).
- Different tax bases (corporate income vs withholding vs unemployment vs franchise/sales).
- A return vs its SEPARATE payment, or a registration vs an ongoing return vs a renewal, when listed as distinct obligations.
- An ongoing COMPLIANCE CONTROL vs a distinct periodic FILING/REPORT, even on the same topic: e.g. the "AML Compliance Programme" (control) and the "REP-CRIM Financial Crime Report" (filing) are DIFFERENT obligations — do not merge a control into its related report. Only merge two phrasings of the SAME control, or two phrasings of the SAME filing.

Indices are 1-based and refer to the numbered list provided. Use each index at most ONCE across all clusters and redundant_parents, and only output entries that actually remove something."""


class FilingDupeCluster(BaseModel):
    keep_index: int = Field(
        description="1-based index of the obligation to KEEP (clearest, most specific, canonical name)."
    )
    drop_indices: list[int] = Field(
        default_factory=list,
        description="1-based indices of entries that are the SAME obligation as keep_index and should be removed.",
    )


class FilingDedupe(BaseModel):
    clusters: list[FilingDupeCluster] = Field(default_factory=list)
    redundant_parents: list[int] = Field(
        default_factory=list,
        description=(
            "1-based indices of GENERIC parent obligations to remove because the "
            "list also contains the SPECIFIC child obligations they summarise "
            "(e.g. a generic multi-state license renewal when the per-state "
            "renewals are present). Only when the children are present."
        ),
    )


def dedupe_filings(filings_block: str, *, model: str = "claude-opus-4-8") -> FilingDedupe:
    """Cluster the duplicate filings in a numbered list. Returns the clusters of
    indices that denote the same underlying filing (one kept, the rest dropped)."""
    if not is_live():
        raise RuleExtractorUnavailable(
            "AI dedupe requires COMPLIANCE_AGENT_LIVE=1 plus an API key."
        )
    client = make_client()
    response = client.messages.parse(
        model=model,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=[
            {
                "type": "text",
                "text": DEDUPE_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": "FILINGS:\n" + filings_block}],
        output_format=FilingDedupe,
    )
    log_usage(response, model=model, label="filing dedupe")
    return response.parsed_output or FilingDedupe()


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
- `jurisdiction_code` — the country as a short code. Prefer one of these existing slugs when it fits: india, uk, us, uae, singapore, lithuania, canada, eu. For ANY OTHER country use its ISO 3166-1 alpha-2 lowercase code (e.g. br, de, jp, za). Use null only if the country is genuinely unknown.
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
    model: str = "claude-opus-4-8",
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
    log_usage(response, model=model, label="license metadata")
    if response.parsed_output is None:
        raise RuntimeError(
            f"License metadata extraction failed — stop_reason={response.stop_reason}."
        )
    return response.parsed_output
