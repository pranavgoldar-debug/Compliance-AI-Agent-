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


class FindingStatus(str, Enum):
    pass_ = "pass"
    warning = "warning"
    fail = "fail"


class VerificationFinding(BaseModel):
    requirement_id: str = Field(description="The `requirement_id` from the extraction this finding pertains to.")
    status: FindingStatus = Field(
        description="`pass` if the requirement is faithful to the source; `warning` for minor issues (imprecise summary, mislabeled severity); `fail` for hallucinated, unsupported, or materially misrepresented requirements."
    )
    quote_verbatim: bool = Field(
        description="Whether `source_quote` appears verbatim in the source document (whitespace-normalized). Set by the verifier, not the model."
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Specific defects: hallucinated obligation, summary contradicts source, severity miscalibrated, etc.",
    )
    suggested_fix: Optional[str] = Field(
        default=None,
        description="Concrete change that would make the requirement pass — e.g. 'lower severity to medium', 'remove — not supported by source'.",
    )


class VerificationResult(BaseModel):
    findings: list[VerificationFinding]
    overall_summary: str = Field(
        description="One-paragraph summary of extraction quality: counts of pass/warning/fail, any systemic issues."
    )
    missed_requirements: list[str] = Field(
        default_factory=list,
        description="Obligations present in the source that were not extracted. Each entry is a short description plus a source quote.",
    )
