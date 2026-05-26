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

export type EffortBand = "1w" | "2w" | "4w" | "8w" | "12w";

export interface UserBrief {
  id: number;
  email: string;
  full_name: string;
  role: Role;
}

export interface Entity {
  id: number;
  name: string;
  legal_type: string;
  jurisdiction_code: string;
  registration_number: string | null;
  incorporation_date: string | null;
  fiscal_year_end: string | null;
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
  status: RuleStatus;
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
  rule_frequency: string;
  rule_due_date_rule: string | null;
  rule_source_url: string | null;
  entity_name: string;
  entity_jurisdiction_code: string;
  due_date: string;
  period_label: string | null;
  status: ObligationStatus;
  assignee: UserBrief | null;
  effort_band: EffortBand;
  effort_band_reason: string | null;
  filing_reference: string | null;
  payment_amount: string | null;
  payment_reference: string | null;
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
  | "Formation"
  | "Filings"
  | "Contracts"
  | "Expert notes"
  | "Other";

export const DOCUMENT_CATEGORIES: DocumentCategory[] = [
  "Formation",
  "Filings",
  "Contracts",
  "Expert notes",
  "Other",
];

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
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}
