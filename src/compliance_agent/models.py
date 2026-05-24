from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    informational = "informational"


class ComplianceRequirement(BaseModel):
    requirement_id: str = Field(
        description="Stable identifier extracted from the source (e.g. 'GDPR Art. 5(1)(a)', 'SOC2 CC6.1'). If the source has no identifier, synthesize one from the section heading."
    )
    title: str = Field(description="Short human-readable title (under 120 chars).")
    summary: str = Field(description="One- to three-sentence plain-language summary of the obligation.")
    source_quote: str = Field(
        description="Verbatim sentence(s) from the source document that establish this requirement."
    )
    category: str = Field(
        description="Topical category — e.g. 'access_control', 'data_retention', 'incident_response', 'audit_logging', 'encryption', 'training', 'vendor_management'."
    )
    severity: Severity = Field(description="Operational severity if the requirement is not met.")
    applies_to: list[str] = Field(
        default_factory=list,
        description="Roles, systems, or data categories the requirement applies to (e.g. 'production databases', 'all employees', 'PII').",
    )
    evidence_artifacts: list[str] = Field(
        default_factory=list,
        description="Concrete artifacts an auditor would request to verify compliance (e.g. 'access review logs', 'penetration test report').",
    )
    section_reference: Optional[str] = Field(
        default=None,
        description="Section or page reference in the source document, if identifiable.",
    )


class ExtractionResult(BaseModel):
    document_title: str = Field(description="Inferred title of the source document.")
    framework: Optional[str] = Field(
        default=None,
        description="Compliance framework if identifiable (e.g. 'SOC 2', 'HIPAA', 'GDPR', 'PCI DSS', 'ISO 27001'). Null if the document is an internal policy.",
    )
    requirements: list[ComplianceRequirement]
    extraction_notes: Optional[str] = Field(
        default=None,
        description="Caveats, ambiguities, or sections that need human review.",
    )
