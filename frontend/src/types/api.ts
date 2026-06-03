// TypeScript mirror of the Pydantic schemas in src/compliance_agent/api/schemas.py

export type Role = "admin" | "employee";

export type ObligationStatus =
  | "not_started"
  | "in_progress"
  | "pending_review"
  | "completed"
  | "not_applicable";

export type RuleStatus = "production" | "staging" | "archived";

export type Applicability = "Mandatory" | "Conditional" | "Sector-specific";

export type TaxType = "Direct Tax" | "Indirect Tax" | "Not a Tax";

export type EffortBand = "1w" | "2w" | "4w" | "8w" | "12w";

export type Department =
  | "compliance"
  | "finance"
  | "legal"
  | "risk"
  | "operations";

export interface UserBrief {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  department?: Department | null;
}

export interface Entity {
  id: number;
  name: string;
  legal_type: string;
  jurisdiction_code: string;
  short_code: string | null;
  registration_number: string | null;
  incorporation_date: string | null;
  fiscal_year_end: string | null;
  finance_profile: Record<string, string> | null;
  country_lead: UserBrief | null;
  archived_at: string | null;
  created_at: string;
  active_obligations_count: number;
  overdue_obligations_count: number;
  in_alert_window_count: number;
  last_filed_at: string | null;
}

export interface Rule {
  id: number;
  name: string;
  jurisdiction_code: string;
  category: string;
  area: string;
  form_name: string;
  authority: string;
  frequency: string;
  due_date_rule: string;
  payment_rule: string | null;
  applicability: Applicability;
  applicability_note: string | null;
  tax_type: TaxType;
  status: RuleStatus;
  source_url: string | null;
  submission_url: string | null;
  source_text: string | null;
  source_changed_at: string | null;
  entity_ids: number[];
  created_at: string;
  updated_at: string;
}

export interface Obligation {
  id: number;
  rule_id: number;
  entity_id: number;
  rule_name: string;
  rule_form_name: string;
  rule_authority: string;
  rule_category: string;
  rule_tax_type: TaxType;
  rule_responsible_function: string | null;
  rule_frequency: string;
  rule_due_date_rule: string | null;
  rule_source_url: string | null;
  rule_submission_url: string | null;
  rule_source_changed_at: string | null;
  rule_payment_rule: string | null;
  entity_name: string;
  entity_jurisdiction_code: string;
  due_date: string;
  period_label: string | null;
  status: ObligationStatus;
  department: "compliance" | "finance" | "legal" | "risk" | "operations";
  assignee: UserBrief | null;
  effort_band: EffortBand;
  effort_band_reason: string | null;
  filing_reference: string | null;
  payment_amount: string | null;
  payment_reference: string | null;
  clickup_task_url: string | null;
  beneficiary_details: string | null;
  is_awaiting_payment: boolean;
  notes: string | null;
  days_remaining: number;
  is_overdue: boolean;
  is_in_alert_window: boolean;
  next_alert_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CalendarObligation {
  id: number;
  due_date: string;
  status: ObligationStatus;
  entity_id: number;
  entity_name: string;
  entity_jurisdiction_code: string;
  rule_form_name: string;
  rule_authority: string;
  rule_category: string;
  rule_tax_type: TaxType;
  rule_applicability: string;
  effort_band: EffortBand;
  assignee: UserBrief | null;
  is_overdue: boolean;
  is_in_alert_window: boolean;
  days_remaining: number;
}

export interface DashboardStats {
  overdue: number;
  in_alert_window: number;
  in_safe_zone: number;
  completed_this_month: number;
  due_this_week: number;
  due_this_month: number;
  unassigned: number;
  entity_count: number;
  license_count: number;
  awaiting_review: number;
  awaiting_payment: number;
  open_tasks: Obligation[];
  items_in_alert_window: Obligation[];
  this_week: Obligation[];
}

export interface Comment {
  id: number;
  obligation_id: number;
  author: UserBrief;
  body: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Phase 5 — documents, activities, users
// ---------------------------------------------------------------------------
export type DocumentCategory =
  | "Filings"
  | "Templates"
  // Legacy values kept so existing rows render. Don't surface in pickers.
  | "Formation"
  | "Contracts"
  | "Expert notes"
  | "Other";

// Categories shown as upload targets / cards. Trimmed to the two that
// actually matter for the current workflow — filings (proofs of filing)
// and templates (blank forms and reusable assets).
export const DOCUMENT_CATEGORIES: DocumentCategory[] = ["Filings", "Templates"];

export interface DocumentOut {
  id: number;
  entity_id: number;
  entity_name: string | null;
  obligation_id: number | null;
  obligation_form_name: string | null;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  category: DocumentCategory;
  tags: string | null;
  url: string | null;
  uploaded_by: UserBrief | null;
  created_at: string;
}

export interface ActivityOut {
  id: number;
  actor: UserBrief | null;
  action: string;
  target_type: string | null;
  target_id: number | null;
  target_label: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface UserOut {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  department: Department | null;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

// ---------------------------------------------------------------------------
// Phase 6 — notifications, bulk, system info
// ---------------------------------------------------------------------------
export type NotificationKind =
  | "mention"
  | "assigned"
  | "overdue"
  | "alert_window"
  | "status_change"
  | "payment_request";

export interface NotificationOut {
  id: number | null;
  kind: NotificationKind;
  title: string;
  body: string | null;
  link_url: string | null;
  obligation_id: number | null;
  actor: UserBrief | null;
  read: boolean;
  created_at: string;
}

export interface SystemInfo {
  mode: "live" | "mock";
  ai_available: boolean;
  backend: "anthropic" | "openrouter" | "mock";
  version: string;
}

export interface BulkUpdateResult {
  updated: number;
  skipped: number[];
}

// ---------------------------------------------------------------------------
// Phase 7 — AI assist
// ---------------------------------------------------------------------------
export interface DocumentExtractionSuggestion {
  filing_reference: string | null;
  payment_amount: string | null;
  payment_reference: string | null;
  completed_at: string | null;
  notes_suggestion: string | null;
  confidence: "high" | "medium" | "low";
}

export interface DocumentExtractionResult {
  available: boolean;
  excerpt: string | null;
  suggestion: DocumentExtractionSuggestion | null;
  error: string | null;
}

export interface SecondOpinion {
  verdict: "approve" | "needs_more_info" | "reject";
  confidence: "high" | "medium" | "low";
  reasoning: string;
  suggested_next_steps: string[];
  risk_flags: string[];
}

export interface SecondOpinionResult {
  available: boolean;
  opinion: SecondOpinion | null;
  error: string | null;
}

export interface RuleSourceCheckResult {
  fetched_at: string;
  http_status: number | null;
  error: string | null;
  changed: boolean;
  is_first_snapshot: boolean;
  content_length: number;
  content_hash: string | null;
  new_excerpt: string | null;
  prev_excerpt: string | null;
  diff_excerpt: string | null;
  change_summary: string | null;
}

export interface RuleSnapshot {
  id: number;
  rule_id: number;
  fetched_at: string;
  fetched_by: UserBrief | null;
  http_status: number | null;
  content_length: number;
  content_hash: string;
  content_excerpt: string | null;
  change_summary: string | null;
}

// ---------------------------------------------------------------------------
// Regulation Library (the original "agent" surface — pick a regulation, see
// every obligation it imposes with severity, source quote, evidence artifacts)
// ---------------------------------------------------------------------------
export type Severity = "critical" | "high" | "medium" | "low" | "informational";

export type FindingStatus = "pass" | "warning" | "fail";

export interface RegulationSummary {
  id: string;
  name: string;
  short_name: string;
  scope: string;
  framework: string | null;
  text_resource: string;
}

export interface CountrySummary {
  code: string;
  name: string;
  flag: string;
  regulations: RegulationSummary[];
}

export interface ComplianceRequirement {
  requirement_id: string;
  title: string;
  summary: string;
  source_quote: string;
  category: string;
  severity: Severity;
  applies_to: string[];
  evidence_artifacts: string[];
  section_reference: string | null;
}

export interface ExtractionResult {
  document_title: string;
  framework: string | null;
  requirements: ComplianceRequirement[];
  extraction_notes: string | null;
}

export interface VerificationFinding {
  requirement_id: string;
  status: FindingStatus;
  quote_verbatim: boolean;
  issues: string[];
  suggested_fix: string | null;
}

export interface VerificationResult {
  findings: VerificationFinding[];
  overall_summary: string;
  missed_requirements: string[];
}

export interface RegulationView {
  country: string;
  country_code: string;
  flag: string;
  regulation: RegulationSummary;
  extraction: ExtractionResult;
  verification: VerificationResult | null;
}

// -----------------------------------------------------------------------
// Licenses
// -----------------------------------------------------------------------
export type LicenseExpiryStatus = "valid" | "expiring" | "expired" | "unknown";

export interface License {
  id: number;
  entity_id: number;
  entity_name: string;
  name: string;
  license_type: string;
  authority: string;
  jurisdiction_code: string;
  license_number: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  notes: string | null;
  has_file: boolean;
  filename: string | null;
  size_bytes: number;
  content_type: string | null;
  created_at: string;
  updated_at: string;
  expiry_status: LicenseExpiryStatus;
  days_to_expiry: number | null;
}

export interface LicenseAssignee {
  id: number;
  email: string;
  full_name: string | null;
}

export interface LicenseRuleHit {
  id: number;
  name: string;
  form_name: string;
  authority: string;
  category: string;
  area: string;
  frequency: string;
  due_date_rule: string;
  payment_rule: string | null;
  applicability: string;
  responsible_function: string | null;
  plain_description: string | null;
  tax_type: string;
  relevance: "direct" | "entity";
  match_reason: string | null;
  next_obligation_id: number | null;
  next_due_date: string | null;
  projected_due_date: string | null;
  next_status: string | null;
  next_assignee: LicenseAssignee | null;
  days_to_next: number | null;
}

export interface ApplicableRulesResponse {
  license_id: number;
  direct: LicenseRuleHit[];
  entity_other: LicenseRuleHit[];
  counts: Record<string, number>;
}
