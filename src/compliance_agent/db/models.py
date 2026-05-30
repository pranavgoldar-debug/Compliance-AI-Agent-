"""SQLAlchemy models for Aspora Compliance OS.

Tables:
  users           — login accounts (admin / employee)
  entities        — legal entities (Aspora UK Ltd, Aspora DMCC, ...)
  rules           — compliance rule templates (e.g. India GSTR-3B monthly)
  rule_entities   — many-to-many: rule applies to which entities
  obligations     — concrete per-entity-per-period instances of a rule
                    (status, due date, assignee, filing reference, payment)
  comments        — comments on an obligation
  activities     — audit log of user actions
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from compliance_agent.db.base import Base


class Role(str, enum.Enum):
    admin = "admin"
    employee = "employee"


class ObligationStatus(str, enum.Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    pending_review = "pending_review"
    completed = "completed"
    not_applicable = "not_applicable"


class Department(str, enum.Enum):
    """Owning team for an obligation. Drives the Workspace's department
    filter and (later) Slack routing + escalation chains."""
    compliance = "compliance"  # files returns, manages regulatory submissions
    finance = "finance"        # pays bills, verifies payment references
    legal = "legal"            # reviews contracts, opinions, change notifications
    risk = "risk"              # risk-assessment outputs, audits
    operations = "operations"  # day-to-day operational tasks


class RuleStatus(str, enum.Enum):
    production = "production"
    staging = "staging"
    archived = "archived"


class Applicability(str, enum.Enum):
    mandatory = "Mandatory"
    conditional = "Conditional"
    sector_specific = "Sector-specific"


class EffortBand(str, enum.Enum):
    """Lead-time band for an obligation. Alerts fire at ~2× this window
    before the due date (e.g. a 4-week band → alert 8 weeks out)."""
    w1 = "1w"
    w2 = "2w"
    w4 = "4w"
    w8 = "8w"
    w12 = "12w"


# How many days each effort band represents (lead-time = 2× this).
EFFORT_BAND_DAYS: dict[EffortBand, int] = {
    EffortBand.w1: 7,
    EffortBand.w2: 14,
    EffortBand.w4: 28,
    EffortBand.w8: 56,
    EffortBand.w12: 84,
}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    role: Mapped[Role] = mapped_column(SAEnum(Role), nullable=False, default=Role.employee)
    # Which team this user belongs to. Drives the assign-to-team flow:
    # admin assigns compliance work to compliance-tagged users; once the
    # filing is approved, admin hands off the payment leg to finance-tagged
    # users. Nullable — legacy users + admins can be untagged.
    department: Mapped[Optional[Department]] = mapped_column(
        SAEnum(Department), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Reverse-side relationships
    # Notification preferences — Phase 9 integrations.
    notify_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_slack: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Personal Slack member id (e.g. U0123ABCD). When set, our channel-wide
    # webhook pings can <@-mention> this user. Optional.
    slack_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    led_entities: Mapped[list["Entity"]] = relationship(
        "Entity", back_populates="country_lead", foreign_keys="Entity.country_lead_id"
    )
    assigned_obligations: Mapped[list["Obligation"]] = relationship(
        "Obligation", back_populates="assignee", foreign_keys="Obligation.assignee_id"
    )

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role.value})>"


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    legal_type: Mapped[str] = mapped_column(String(120), nullable=False, default="")  # e.g. Private Limited
    jurisdiction_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # india / uk / us / uae / sg / lt / ca / eu
    # Short internal code from the tracker (VINC, RTUK, NESS, ...) — used
    # for cross-referencing rows in the Aspora Global Compliance Tracker.
    short_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    registration_number: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    incorporation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    fiscal_year_end: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # "31-Mar", "31-Dec"

    country_lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    country_lead: Mapped[Optional[User]] = relationship(
        "User", back_populates="led_entities", foreign_keys=[country_lead_id]
    )

    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    obligations: Mapped[list["Obligation"]] = relationship("Obligation", back_populates="entity")
    rules: Mapped[list["Rule"]] = relationship(
        "Rule",
        secondary="rule_entities",
        back_populates="entities",
    )

    def __repr__(self) -> str:
        return f"<Entity {self.name} ({self.jurisdiction_code})>"


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
class Rule(Base):
    """A compliance rule template (e.g. 'India GSTR-3B, monthly, 20th').

    Rules are admin-managed. Each rule, when associated with one or more
    entities (via `rule_entities`), can generate concrete Obligation rows
    for each entity for each due-date period.
    """
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    jurisdiction_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    area: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    form_name: Mapped[str] = mapped_column(String(255), nullable=False)
    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    frequency: Mapped[str] = mapped_column(String(120), nullable=False)
    due_date_rule: Mapped[str] = mapped_column(Text, nullable=False)
    payment_rule: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applicability: Mapped[Applicability] = mapped_column(
        SAEnum(Applicability), nullable=False, default=Applicability.mandatory
    )
    applicability_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[RuleStatus] = mapped_column(
        SAEnum(RuleStatus), nullable=False, default=RuleStatus.production, index=True
    )

    # Source provenance — used by the regulation change watcher (Phase 7).
    # source_url   = informational page (regulation text + form template).
    #                Visible to everyone in the team.
    # submission_url = portal where the filing is actually submitted.
    #                  Admin-only. Often the same host as source_url but a
    #                  different path (e.g. an e-filing portal vs. the
    #                  rule's circular page).
    source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    submission_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    source_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    entities: Mapped[list[Entity]] = relationship(
        "Entity", secondary="rule_entities", back_populates="rules"
    )
    obligations: Mapped[list["Obligation"]] = relationship("Obligation", back_populates="rule")


class RuleEntity(Base):
    """Many-to-many join: which entities a rule applies to."""
    __tablename__ = "rule_entities"

    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id", ondelete="CASCADE"), primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)


# ---------------------------------------------------------------------------
# Obligations
# ---------------------------------------------------------------------------
class Obligation(Base):
    """Concrete per-entity, per-period instance of a Rule.

    e.g. Rule = "India GSTR-3B monthly"; for Aspora India Pvt Ltd, this
    spawns one Obligation per month with due_date = 20th of next month.
    """
    __tablename__ = "obligations"
    __table_args__ = (
        # Avoid duplicate rows if generation runs twice. PR-B added the
        # department leg — a single filing now spawns one compliance row
        # (filing) and optionally one finance row (payment) per due_date,
        # so the unique key includes department.
        UniqueConstraint(
            "rule_id", "entity_id", "due_date", "department",
            name="uq_obligation_rule_entity_date_dept",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False, index=True)

    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_label: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)  # "Apr 2026", "Q1 FY26"

    status: Mapped[ObligationStatus] = mapped_column(
        SAEnum(ObligationStatus), nullable=False, default=ObligationStatus.not_started, index=True
    )
    department: Mapped[Department] = mapped_column(
        SAEnum(Department), nullable=False, default=Department.compliance, index=True
    )
    effort_band: Mapped[EffortBand] = mapped_column(
        SAEnum(EffortBand), nullable=False, default=EffortBand.w4
    )
    effort_band_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assignee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    assignee: Mapped[Optional[User]] = relationship(
        "User", back_populates="assigned_obligations", foreign_keys=[assignee_id]
    )

    filing_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_amount: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Bank account / beneficiary info finance uses to actually move the
    # money — kept as free text so we don't have to model every payment
    # rail's quirks. Visible only on the finance side of the obligation
    # detail.
    beneficiary_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    rule: Mapped[Rule] = relationship("Rule", back_populates="obligations")
    entity: Mapped[Entity] = relationship("Entity", back_populates="obligations")
    comments: Mapped[list["Comment"]] = relationship(
        "Comment", back_populates="obligation", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Comments + Activity log
# ---------------------------------------------------------------------------
class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    obligation_id: Mapped[int] = mapped_column(
        ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    obligation: Mapped[Obligation] = relationship("Obligation", back_populates="comments")
    author: Mapped[User] = relationship("User")


class Activity(Base):
    """Audit trail of user actions across the app."""
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    target_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )

    actor: Mapped[Optional[User]] = relationship("User")


# ---------------------------------------------------------------------------
# Documents — uploaded files attached to entities and/or obligations
# ---------------------------------------------------------------------------
class DocumentCategory(str, enum.Enum):
    # Active categories — surfaced in the UI as upload targets.
    filings = "Filings"
    templates = "Templates"
    # Legacy values kept so existing rows in the DB don't fail to load.
    # They no longer appear as upload-target cards; users can still see
    # any rows in those categories via the entity's full document list.
    formation = "Formation"
    contracts = "Contracts"
    expert_notes = "Expert notes"
    other = "Other"


class NotificationKind(str, enum.Enum):
    mention = "mention"
    assigned = "assigned"
    overdue = "overdue"           # derived on read; not persisted
    alert_window = "alert_window" # derived on read; not persisted
    status_change = "status_change"
    payment_request = "payment_request"  # filing approved → finance asked to pay


class Document(Base):
    """A file uploaded to the system. Always attached to one entity; optionally
    to a specific obligation as proof-of-filing."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    obligation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("obligations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Filename the user uploaded; preserved for display.
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    # On-disk relative path (under uploads/) — opaque, not user-facing.
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category: Mapped[DocumentCategory] = mapped_column(
        SAEnum(DocumentCategory), nullable=False, default=DocumentCategory.other, index=True
    )
    tags: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # comma-separated

    uploaded_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )

    entity: Mapped[Entity] = relationship("Entity")
    obligation: Mapped[Optional[Obligation]] = relationship("Obligation")
    uploaded_by: Mapped[Optional[User]] = relationship("User")


# ---------------------------------------------------------------------------
# Notifications — in-app inbox (Phase 6)
# ---------------------------------------------------------------------------
class Notification(Base):
    """An item in a user's notification inbox.

    Persisted kinds (mention / assigned / status_change) live in this table.
    Live-derived kinds (overdue / alert_window) are computed on read from
    the user's open obligations and never stored.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[NotificationKind] = mapped_column(
        SAEnum(NotificationKind), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Where the notification deep-links (e.g. /obligations/123).
    link_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    obligation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("obligations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    comment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("comments.id", ondelete="SET NULL"), nullable=True
    )
    actor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )

    actor: Mapped[Optional[User]] = relationship("User", foreign_keys=[actor_id])
    obligation: Mapped[Optional[Obligation]] = relationship("Obligation")


# ---------------------------------------------------------------------------
# Rule source snapshots — Phase 7 regulation change watcher
# ---------------------------------------------------------------------------
class RuleSnapshot(Base):
    """A captured fetch of a rule's source_url. We compare new fetches against
    the latest snapshot's content_hash to detect upstream changes."""

    __tablename__ = "rule_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
    fetched_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # First ~16 KB of plain text — enough for a diff preview without bloating SQLite.
    content_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # AI-summarised description of what changed vs the prior snapshot (optional).
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    rule: Mapped[Rule] = relationship("Rule")
    fetched_by: Mapped[Optional[User]] = relationship("User")


# ---------------------------------------------------------------------------
# Password reset tokens — Phase 8
# ---------------------------------------------------------------------------
class PasswordResetToken(Base):
    """Single-use token for the forgot-password flow.

    We store only the SHA-256 hash of the token — the raw value is shown to
    the user once (via email or admin-portal link) and never persisted in
    plain text. The active lookup compares hash(incoming_token).
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    # For audit: IP / user-agent that requested the token. Best-effort.
    requester_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    requester_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship("User")


# ---------------------------------------------------------------------------
# Workspace settings — singleton-ish key/value table for integration config.
# Stored as JSON so we don't have to migrate every time a new integration
# adds a config knob.
# ---------------------------------------------------------------------------
class WorkspaceSetting(Base):
    __tablename__ = "workspace_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    updated_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )


# ---------------------------------------------------------------------------
# Licenses
#
# A license is an authorisation an entity holds from a regulator (e.g. FCA
# permission, DMCC trade license, CBUAE SVF licence). It pins a regulator +
# jurisdiction to an entity, so the app can surface "for this license, which
# filings do you owe?" — driven off the rules that match the same
# jurisdiction and authority.
# ---------------------------------------------------------------------------
class License(Base):
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Free-text license type — e.g. "FCA Authorisation", "DMCC Trade License",
    # "CBUAE SVF licence", "Lithuania EMI". Used for matching + display.
    license_type: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    jurisdiction_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    license_number: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Optional uploaded license file — reuses the documents storage layer.
    filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    entity: Mapped[Entity] = relationship("Entity")
