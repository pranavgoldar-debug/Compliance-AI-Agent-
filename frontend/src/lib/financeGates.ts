// Find Regulations qualifying questions — a branching, jurisdiction-aware
// questionnaire. Each "gate" maps to a finance filing area: answer the gate,
// and on "yes" one or two follow-ups appear to pin down mandatory-vs-conditional
// detail (frequency, threshold, customer funds, …). The answers are stored on
// the entity (finance_profile) and fed to Claude, which uses them to label each
// filing Mandatory or Conditional — nothing is ever dropped.
//
// Keys here MUST match `_PROFILE_QUESTIONS` in the backend
// (src/compliance_agent/api/licenses.py) so the prompt renders them.

export type GateOption = { value: string; label: string };

export type FollowUp = {
  key: string;
  question: string;
  options: GateOption[];
  // Some follow-ups only make sense in certain jurisdictions (e.g. WPS in UAE).
  jurisdictions?: string[];
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
];
const YES_NO_UNSURE: GateOption[] = [...YES_NO, { value: "unsure", label: "Not sure" }];
const BAND: GateOption[] = [
  { value: "below", label: "Below threshold" },
  { value: "above", label: "Above threshold" },
  { value: "unsure", label: "Not sure" },
];

// Ordered list of gates. Jurisdiction filtering decides which ones show; gates
// with no `jurisdictions` apply everywhere (the generic finance fallback).
export const FINANCE_GATES: FilingGate[] = [
  {
    id: "vat",
    drives: "VAT / GST Return",
    key: "vat_registered",
    question: "Is the entity registered for VAT / GST?",
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
    id: "payroll",
    drives: "Payroll / withholding / WPS",
    key: "employs_staff",
    question: "Does the entity employ staff on payroll?",
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
        question: "Does it contribute to pension / social security (e.g. GPSSA)?",
        options: YES_NO,
      },
    ],
  },
  {
    id: "corporate_tax",
    drives: "Corporate Tax registration + return",
    key: "ct_registered",
    question: "Is the entity registered for corporate / income tax?",
    options: YES_NO_UNSURE,
    followups: [
      {
        key: "ct_income_band",
        question: "Is taxable income above the local corporate-tax threshold?",
        options: BAND,
      },
    ],
  },
  {
    id: "transfer_pricing",
    drives: "Transfer Pricing disclosure / Master & Local File",
    key: "related_party",
    question: "Does it have related-party or intra-group transactions?",
    options: YES_NO,
    followups: [
      {
        key: "tp_threshold",
        question: "Are those transactions above the TP documentation threshold?",
        options: BAND,
      },
    ],
  },
  {
    id: "licensed_activity",
    drives: "Safeguarding / client-money audit",
    key: "licensed_activity",
    question: "Does it carry on a licensed / regulated financial activity?",
    options: YES_NO,
    jurisdictions: ["uk", "uae"],
    followups: [
      {
        key: "client_funds",
        question: "Does it hold client / customer funds?",
        options: YES_NO,
      },
    ],
  },
  {
    id: "esr",
    drives: "Economic Substance (ESR) Notification + Report",
    key: "esr_activity",
    question: 'Does it conduct a "relevant activity" under ESR?',
    options: YES_NO,
    jurisdictions: ["uae"],
    followups: [
      {
        key: "esr_income",
        question: "Does it earn income from that relevant activity?",
        options: YES_NO,
      },
    ],
  },
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
