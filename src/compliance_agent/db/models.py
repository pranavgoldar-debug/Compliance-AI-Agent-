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
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Reverse-side relationships
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
    jurisdiction_code: Mapped[str] = mapped_column(String(8), nullable=False, index=True)  # india / uk / us / uae / sg / lt / ca / eu
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
    jurisdiction_code: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
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
        # Avoid duplicate (rule, entity, due_date) rows if generation runs twice.
        UniqueConstraint("rule_id", "entity_id", "due_date", name="uq_obligation_rule_entity_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False, index=True)

    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_label: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)  # "Apr 2026", "Q1 FY26"

    status: Mapped[ObligationStatus] = mapped_column(
        SAEnum(ObligationStatus), nullable=False, default=ObligationStatus.not_started, index=True
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
    formation = "Formation"
    filings = "Filings"
    contracts = "Contracts"
    expert_notes = "Expert notes"
    other = "Other"


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
