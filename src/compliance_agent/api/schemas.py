"""Pydantic schemas for the Aspora Compliance OS API surface."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from compliance_agent.db import (
    Applicability,
    DocumentCategory,
    EffortBand,
    ObligationStatus,
    Role,
    RuleStatus,
    TaxType,
)


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class UserBrief(_Base):
    id: int
    email: str
    full_name: str
    role: Role
    department: Optional[str] = None


class UserOut(_Base):
    id: int
    email: str
    full_name: str
    role: Role
    department: Optional[str] = None
    is_active: bool
    department: Optional[str] = None
    created_at: datetime
    last_login_at: Optional[datetime] = None


class UserCreate(BaseModel):
    email: str
    full_name: str
    role: Role = Role.employee
    department: Optional[str] = None
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[Role] = None
    department: Optional[str] = None  # set to "" or omit to clear
    is_active: Optional[bool] = None
    department: Optional[str] = None
    password: Optional[str] = None  # admin password reset


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
class EntityCreate(BaseModel):
    name: str
    legal_type: str = ""
    jurisdiction_code: str
    short_code: Optional[str] = None
    registration_number: Optional[str] = None
    incorporation_date: Optional[date] = None
    fiscal_year_end: Optional[str] = None
    country_lead_id: Optional[int] = None


class EntityUpdate(BaseModel):
    name: Optional[str] = None
    legal_type: Optional[str] = None
    jurisdiction_code: Optional[str] = None
    short_code: Optional[str] = None
    registration_number: Optional[str] = None
    incorporation_date: Optional[date] = None
    fiscal_year_end: Optional[str] = None
    country_lead_id: Optional[int] = None
    finance_profile: Optional[dict] = None
    ownership: Optional[list] = None


class EntityOut(_Base):
    id: int
    name: str
    legal_type: str
    jurisdiction_code: str
    short_code: Optional[str] = None
    registration_number: Optional[str] = None
    incorporation_date: Optional[date] = None
    fiscal_year_end: Optional[str] = None
    finance_profile: Optional[dict] = None
    ownership: Optional[list] = None
    country_lead: Optional[UserBrief] = None
    archived_at: Optional[datetime] = None
    created_at: datetime
    active_obligations_count: int = 0
    overdue_obligations_count: int = 0
    in_alert_window_count: int = 0
    last_filed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
class RuleCreate(BaseModel):
    name: str
    jurisdiction_code: str
    category: str
    area: str = ""
    form_name: str
    authority: str
    frequency: str
    due_date_rule: str
    payment_rule: Optional[str] = None
    applicability: Applicability = Applicability.mandatory
    applicability_note: Optional[str] = None
    tax_type: TaxType = TaxType.not_tax
    responsible_function: Optional[str] = None
    plain_description: Optional[str] = None
    status: RuleStatus = RuleStatus.production
    source_url: Optional[str] = None
    submission_url: Optional[str] = None
    source_text: Optional[str] = None
    entity_ids: list[int] = []


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    jurisdiction_code: Optional[str] = None
    category: Optional[str] = None
    area: Optional[str] = None
    form_name: Optional[str] = None
    authority: Optional[str] = None
    frequency: Optional[str] = None
    due_date_rule: Optional[str] = None
    payment_rule: Optional[str] = None
    applicability: Optional[Applicability] = None
    applicability_note: Optional[str] = None
    tax_type: Optional[TaxType] = None
    responsible_function: Optional[str] = None
    plain_description: Optional[str] = None
    source_url: Optional[str] = None
    submission_url: Optional[str] = None
    source_text: Optional[str] = None
    status: Optional[RuleStatus] = None
    entity_ids: Optional[list[int]] = None
    owner_id: Optional[int] = None
    reviewer_id: Optional[int] = None
    approver_id: Optional[int] = None


class RuleOut(_Base):
    id: int
    name: str
    jurisdiction_code: str
    category: str
    area: str
    form_name: str
    authority: str
    frequency: str
    due_date_rule: str
    payment_rule: Optional[str] = None
    applicability: Applicability
    applicability_note: Optional[str] = None
    tax_type: TaxType = TaxType.not_tax
    responsible_function: Optional[str] = None
    plain_description: Optional[str] = None
    status: RuleStatus
    source_url: Optional[str] = None
    submission_url: Optional[str] = None
    source_text: Optional[str] = None
    source_changed_at: Optional[datetime] = None
    entity_ids: list[int] = []
    owner_id: Optional[int] = None
    reviewer_id: Optional[int] = None
    approver_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class RuleSnapshotOut(_Base):
    id: int
    rule_id: int
    fetched_at: datetime
    fetched_by: Optional[UserBrief] = None
    http_status: Optional[int] = None
    content_length: int
    content_hash: str
    content_excerpt: Optional[str] = None
    change_summary: Optional[str] = None


# ---------------------------------------------------------------------------
# Obligations
# ---------------------------------------------------------------------------
class ObligationUpdate(BaseModel):
    status: Optional[ObligationStatus] = None
    assignee_id: Optional[int] = None
    filing_reference: Optional[str] = None
    payment_amount: Optional[str] = None
    payment_reference: Optional[str] = None
    beneficiary_details: Optional[str] = None
    notes: Optional[str] = None
    due_date: Optional[date] = None
    effort_band: Optional[EffortBand] = None
    effort_band_reason: Optional[str] = None


class CommentOut(_Base):
    id: int
    obligation_id: int
    author: UserBrief
    body: str
    created_at: datetime


class ObligationOut(_Base):
    id: int
    rule_id: int
    entity_id: int
    rule_name: str
    rule_form_name: str
    rule_authority: str
    rule_category: str
    rule_tax_type: TaxType = TaxType.not_tax
    rule_responsible_function: Optional[str] = None
    rule_frequency: str
    rule_due_date_rule: Optional[str] = None
    rule_source_url: Optional[str] = None
    rule_submission_url: Optional[str] = None
    rule_source_changed_at: Optional[datetime] = None
    rule_payment_rule: Optional[str] = None
    entity_name: str
    entity_jurisdiction_code: str
    due_date: date
    period_label: Optional[str] = None
    status: ObligationStatus
    department: str = "compliance"
    assignee: Optional[UserBrief] = None
    effort_band: EffortBand = EffortBand.w4
    effort_band_reason: Optional[str] = None
    filing_reference: Optional[str] = None
    payment_amount: Optional[str] = None
    payment_reference: Optional[str] = None
    clickup_task_url: Optional[str] = None
    beneficiary_details: Optional[str] = None
    is_awaiting_payment: bool = False
    notes: Optional[str] = None
    days_remaining: int = 0
    is_overdue: bool = False
    is_in_alert_window: bool = False
    next_alert_at: Optional[date] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class CommentCreate(BaseModel):
    body: str


# ---------------------------------------------------------------------------
# Dashboard / Calendar
# ---------------------------------------------------------------------------
class DashboardStats(_Base):
    overdue: int
    in_alert_window: int
    in_safe_zone: int
    completed_this_month: int
    due_this_week: int
    due_this_month: int
    unassigned: int
    entity_count: int = 0
    license_count: int = 0
    awaiting_review: int = 0
    awaiting_payment: int = 0
    open_tasks: list[ObligationOut]
    items_in_alert_window: list[ObligationOut]
    this_week: list[ObligationOut]


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
class DocumentOut(_Base):
    id: int
    entity_id: int
    entity_name: Optional[str] = None
    obligation_id: Optional[int] = None
    obligation_form_name: Optional[str] = None
    filename: str
    content_type: Optional[str] = None
    size_bytes: int
    category: DocumentCategory
    tags: Optional[str] = None
    # Set for "link" documents (a template/portal URL rather than an uploaded
    # file). None for normal file uploads.
    url: Optional[str] = None
    uploaded_by: Optional[UserBrief] = None
    created_at: datetime


class DocumentUpdate(BaseModel):
    filename: Optional[str] = None
    category: Optional[DocumentCategory] = None
    tags: Optional[str] = None


class DocumentLinkCreate(BaseModel):
    url: str
    title: Optional[str] = None
    category: Optional[DocumentCategory] = None
    tags: Optional[str] = None


# ---------------------------------------------------------------------------
# Activity feed
# ---------------------------------------------------------------------------
class ActivityOut(_Base):
    id: int
    actor: Optional[UserBrief] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    target_label: Optional[str] = None  # resolved display name (entity/rule/obligation)
    payload: Optional[dict] = None
    created_at: datetime


class CalendarObligation(_Base):
    id: int
    due_date: date
    status: ObligationStatus
    entity_id: int
    entity_name: str
    entity_jurisdiction_code: str
    rule_form_name: str
    rule_authority: str
    rule_category: str
    rule_tax_type: TaxType = TaxType.not_tax
    rule_applicability: str = "Mandatory"  # Mandatory / Conditional / Sector-specific
    effort_band: EffortBand = EffortBand.w4
    assignee: Optional[UserBrief] = None
    is_overdue: bool
    is_in_alert_window: bool = False
    days_remaining: int
