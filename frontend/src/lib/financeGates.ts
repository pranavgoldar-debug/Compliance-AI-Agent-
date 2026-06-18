// Find Regulations qualifying questions — a branching, jurisdiction-aware
// questionnaire. Each "gate" maps to a finance filing area: answer the gate,
// and on "yes" one or two follow-ups appear to pin down mandatory-vs-conditional
// detail (frequency, threshold, customer funds, …). The answers are stored on
// the entity (finance_profile) and fed to Claude, which uses them to label each
// filing Mandatory or Conditional — nothing is ever dropped.
//
// This file is the SINGLE SOURCE OF TRUTH for the questionnaire. The backend
// (`_build_profile_block` in src/compliance_agent/api/licenses.py) renders
// whatever keys/values the saved profile contains — humanising anything it
// doesn't recognise — so you can add / edit / remove questions HERE only,
// without touching the backend. (`_PROFILE_QUESTIONS` there is just optional
// nicer labels.)
//
// To add a question: append a FilingGate below. To make it jurisdiction-
// specific, set `jurisdictions`. To branch, add `followups` (shown on "yes").
// Every yes/no question already offers a "Not applicable" option.

export type GateOption = { value: string; label: string };

export type FollowUp = {
  key: string;
  question: string;
  options: GateOption[];
  // Some follow-ups only make sense in certain jurisdictions (e.g. WPS in UAE).
  jurisdictions?: string[];
  // Jurisdiction-specific threshold figure shown under the question so the user
  // knows the number they're answering against. Keyed by jurisdiction code;
  // `default` is the fallback hint. Headline figures — verify against current
  // local rules before relying on them.
  thresholds?: Record<string, string>;
};

export type FilingGate = {
  id: string;
  // The filing(s) this gate drives — shown as a hint under the question.
  drives: string;
  key: string;
  question: string;
  options: GateOption[];
  // Which jurisdictions show this gate. Omit for "all jurisdictions".
  jurisdictions?: string[];
  // Revealed only when the gate is answered "yes".
  followups?: FollowUp[];
};

const YES_NO: GateOption[] = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
  { value: "na", label: "Not applicable" },
];
const YES_NO_UNSURE: GateOption[] = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
  { value: "unsure", label: "Not sure" },
  { value: "na", label: "Not applicable" },
];
const BAND: GateOption[] = [
  { value: "below", label: "Below threshold" },
  { value: "above", label: "Above threshold" },
  { value: "unsure", label: "Not sure" },
  { value: "na", label: "Not applicable" },
];

// Ordered list of activity gates. Each `id`/`key` is the canonical activity-flag
// id (shared with the regulatory-obligations spec), so a discovered filing's
// `triggering_activity` lines up 1:1 with the answer stored here. Jurisdiction
// filtering decides which ones show; gates with no `jurisdictions` apply
// everywhere. Follow-ups (shown on "yes") pin down mandatory-vs-conditional
// detail (frequency, threshold, …).
export const FINANCE_GATES: FilingGate[] = [
  {
    id: "registered_company",
    drives: "Corporate registry filings, direct tax return / payment",
    key: "registered_company",
    question: "Is this a registered company that files accounts and corporate tax?",
    options: YES_NO,
    followups: [
      {
        key: "ct_income_band",
        question: "Is taxable income above the local corporate-tax threshold?",
        options: BAND,
        thresholds: {
          uae: "UAE: 9% applies above AED 375,000 taxable income (0% below).",
          uk: "UK: 19% up to £50,000; 25% above £250,000 (marginal relief between).",
          india: "India: no income threshold — all company profits are taxable.",
          singapore: "Singapore: flat 17%; partial exemption on the first S$200,000.",
          us: "US: flat 21% federal corporate tax — no threshold.",
          canada: "Canada: small-business rate on active income up to CAD 500,000.",
          lithuania: "Lithuania: standard 15%; reduced rate for revenue under €300,000 & ≤10 staff.",
          eu: "EU: varies by member state — check the local rate threshold.",
          default: "Check the corporate-tax threshold for this jurisdiction.",
        },
      },
    ],
  },
  {
    id: "licensed_financial_activity",
    drives: "Prudential / conduct returns, financial-crime returns, fees",
    key: "licensed_financial_activity",
    question: "Does it hold or operate a financial-services licence?",
    options: YES_NO,
  },
  {
    id: "holds_customer_funds",
    drives: "Safeguarding / client-asset reporting",
    key: "holds_customer_funds",
    question: "Does it hold or safeguard customer funds?",
    options: YES_NO,
  },
  {
    id: "employs_staff",
    drives: "Payroll / employment-tax, social security, pensions",
    key: "employs_staff",
    question: "Does it employ staff and run payroll directly?",
    options: YES_NO,
    followups: [
      {
        key: "wps",
        question: "Are salaries paid through the Wage Protection System (WPS)?",
        options: YES_NO,
        jurisdictions: ["uae"],
      },
      {
        key: "social_security",
        question: "Does it contribute to pension / social security?",
        options: YES_NO,
      },
    ],
  },
  {
    id: "grants_equity",
    drives: "Equity-compensation / share-scheme reporting",
    key: "grants_equity",
    question: "Does it grant equity, options or share-based awards?",
    options: YES_NO,
  },
  {
    id: "takes_foreign_investment",
    drives: "FDI / central-bank inbound-investment reporting",
    key: "takes_foreign_investment",
    question: "Does it receive foreign / cross-border investment?",
    options: YES_NO,
  },
  {
    id: "intra_group_transactions",
    drives: "Transfer-pricing documentation, CbCR / notifications",
    key: "intra_group_transactions",
    question: "Does it transact with other group companies?",
    options: YES_NO,
    followups: [
      {
        key: "tp_threshold",
        question: "Are those transactions above the TP documentation threshold?",
        options: BAND,
        thresholds: {
          uae: "UAE: Local File if revenue ≥ AED 200m; Master File if group revenue ≥ AED 3.15bn.",
          uk: "UK: Master & Local File required for groups with turnover ≥ €750m.",
          india: "India: TP documentation if cross-border related-party transactions exceed ₹1 crore; Master File if group revenue > ₹500 crore.",
          singapore: "Singapore: TP documentation required if gross revenue > S$10m.",
          us: "US: contemporaneous documentation expected for material related-party dealings (no de-minimis).",
          canada: "Canada: contemporaneous documentation if transactions exceed CAD 1m.",
          lithuania: "Lithuania: Local File required if revenue > €3m.",
          eu: "EU: typically aligned to the €750m CbCR group threshold — check locally.",
          default: "Check the transfer-pricing documentation threshold for this jurisdiction.",
        },
      },
    ],
  },
  {
    id: "holds_personal_data",
    drives: "Data-protection registration / fee + breach notification",
    key: "holds_personal_data",
    question: "Does it process personal data of individuals?",
    options: YES_NO,
  },
  {
    id: "vat_gst_registered",
    drives: "Indirect-tax returns",
    key: "vat_gst_registered",
    question: "Is it registered for VAT / GST?",
    options: YES_NO_UNSURE,
    followups: [
      {
        key: "vat_frequency",
        question: "How often is the VAT/GST return filed?",
        options: [
          { value: "monthly", label: "Monthly" },
          { value: "quarterly", label: "Quarterly" },
          { value: "annual", label: "Annual" },
        ],
      },
    ],
  },
  {
    id: "has_owners_controllers",
    drives: "Beneficial-ownership / controller-change filings",
    key: "has_owners_controllers",
    question: "Does it have shareholders / controllers (beneficial owners)?",
    options: YES_NO,
  },
  {
    id: "sanctions_exposure",
    drives: "Sanctions / frozen-asset returns",
    key: "sanctions_exposure",
    question: "Does it move money / have customers (sanctions exposure)?",
    options: YES_NO,
  },
  // ESR (Economic Substance) — shown for ALL jurisdictions per product call.
  // It's primarily a UAE / offshore-centre concept, so for other jurisdictions
  // it's typically answered "Not applicable"; it gates the Economic Substance
  // Notification + Report filings.
  {
    id: "conducts_esr_relevant_activity",
    drives: "Economic Substance (ESR) Notification + Report",
    key: "conducts_esr_relevant_activity",
    question: 'Does it conduct a "relevant activity" under ESR?',
    options: YES_NO,
    followups: [
      {
        key: "esr_income",
        question: "Does it earn income from that relevant activity?",
        options: YES_NO,
      },
    ],
  },
  // Statutory audit — kept as an explicit question (not derived) per product call.
  {
    id: "audit",
    drives: "Audited financial statements",
    key: "audit_required",
    question: "Is a statutory audit required (by regulator or company size)?",
    options: YES_NO_UNSURE,
  },
];

// Gates applicable to a jurisdiction: those with no `jurisdictions` (universal)
// plus those that explicitly list this code.
export function gatesForJurisdiction(code: string | null | undefined): FilingGate[] {
  const c = (code ?? "").toLowerCase();
  return FINANCE_GATES.filter(
    (g) => !g.jurisdictions || g.jurisdictions.includes(c),
  );
}

// Follow-ups of a gate that apply to this jurisdiction.
export function followupsForJurisdiction(
  gate: FilingGate,
  code: string | null | undefined,
): FollowUp[] {
  const c = (code ?? "").toLowerCase();
  return (gate.followups ?? []).filter(
    (f) => !f.jurisdictions || f.jurisdictions.includes(c),
  );
}

// The threshold hint for a follow-up in a given jurisdiction, falling back to
// the `default` entry. Null when the follow-up carries no thresholds.
export function thresholdForJurisdiction(
  followup: FollowUp,
  code: string | null | undefined,
): string | null {
  if (!followup.thresholds) return null;
  const c = (code ?? "").toLowerCase();
  return followup.thresholds[c] ?? followup.thresholds.default ?? null;
}
