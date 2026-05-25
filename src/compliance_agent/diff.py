"""Compute structured diffs between two compliance extractions."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from compliance_agent.models import ComplianceRequirement, ExtractionResult


_SEVERITY_RANK = {
    "informational": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


class RequirementChange(BaseModel):
    requirement_id: str
    changed_fields: list[str] = Field(description="Names of fields that differ between old and new.")
    severity_shift: Optional[str] = Field(
        default=None,
        description="Direction of severity change, e.g. 'medium -> high' or 'critical -> high'. Null if severity unchanged.",
    )
    old: ComplianceRequirement
    new: ComplianceRequirement


class DiffResult(BaseModel):
    old_document_title: str
    new_document_title: str
    added: list[ComplianceRequirement] = Field(description="Requirements in the new document not present in the old.")
    removed: list[ComplianceRequirement] = Field(description="Requirements in the old document not present in the new.")
    changed: list[RequirementChange] = Field(description="Requirements with the same id that differ between versions.")

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)


_COMPARED_FIELDS = (
    "title",
    "summary",
    "source_quote",
    "category",
    "severity",
    "applies_to",
    "evidence_artifacts",
    "section_reference",
)


def _changed_fields(old: ComplianceRequirement, new: ComplianceRequirement) -> list[str]:
    changed: list[str] = []
    for field in _COMPARED_FIELDS:
        old_value = getattr(old, field)
        new_value = getattr(new, field)
        if isinstance(old_value, list) and isinstance(new_value, list):
            if sorted(old_value) != sorted(new_value):
                changed.append(field)
        elif old_value != new_value:
            changed.append(field)
    return changed


def _severity_shift(old: ComplianceRequirement, new: ComplianceRequirement) -> Optional[str]:
    if old.severity == new.severity:
        return None
    direction = "↑" if _SEVERITY_RANK[new.severity.value] > _SEVERITY_RANK[old.severity.value] else "↓"
    return f"{old.severity.value} {direction} {new.severity.value}"


def compute_diff(old: ExtractionResult, new: ExtractionResult) -> DiffResult:
    old_by_id = {r.requirement_id: r for r in old.requirements}
    new_by_id = {r.requirement_id: r for r in new.requirements}

    added = [new_by_id[rid] for rid in new_by_id if rid not in old_by_id]
    removed = [old_by_id[rid] for rid in old_by_id if rid not in new_by_id]

    changed: list[RequirementChange] = []
    for rid in old_by_id.keys() & new_by_id.keys():
        old_req = old_by_id[rid]
        new_req = new_by_id[rid]
        diff_fields = _changed_fields(old_req, new_req)
        if diff_fields:
            changed.append(
                RequirementChange(
                    requirement_id=rid,
                    changed_fields=diff_fields,
                    severity_shift=_severity_shift(old_req, new_req),
                    old=old_req,
                    new=new_req,
                )
            )

    return DiffResult(
        old_document_title=old.document_title,
        new_document_title=new.document_title,
        added=added,
        removed=removed,
        changed=changed,
    )
