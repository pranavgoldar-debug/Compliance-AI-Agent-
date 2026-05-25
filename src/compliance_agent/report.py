"""Render extractions and diffs as human-readable Markdown."""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from compliance_agent.diff import DiffResult, RequirementChange
from compliance_agent.models import (
    ComplianceRequirement,
    ExtractionResult,
    FindingStatus,
    Severity,
    VerificationResult,
)


_SEVERITY_BADGE = {
    Severity.critical: "🔴 CRITICAL",
    Severity.high: "🟠 HIGH",
    Severity.medium: "🟡 MEDIUM",
    Severity.low: "🟢 LOW",
    Severity.informational: "⚪ INFO",
}

_STATUS_BADGE = {
    FindingStatus.pass_: "✅ pass",
    FindingStatus.warning: "⚠️  warning",
    FindingStatus.fail: "❌ fail",
}


def _list(items: list[str]) -> str:
    if not items:
        return "_none_"
    return ", ".join(f"`{item}`" for item in items)


def _render_requirement(req: ComplianceRequirement, finding_md: Optional[str] = None) -> list[str]:
    lines = [
        f"### {req.requirement_id} — {req.title}",
        "",
        f"**Severity:** {_SEVERITY_BADGE[req.severity]}  ",
        f"**Category:** `{req.category}`  ",
        f"**Section:** {req.section_reference or '_unspecified_'}",
        "",
        req.summary,
        "",
        f"**Applies to:** {_list(req.applies_to)}  ",
        f"**Evidence artifacts:** {_list(req.evidence_artifacts)}",
        "",
        "> " + req.source_quote.replace("\n", "\n> "),
        "",
    ]
    if finding_md:
        lines.append(finding_md)
        lines.append("")
    return lines


def render_extraction_markdown(
    extraction: ExtractionResult,
    verification: Optional[VerificationResult] = None,
) -> str:
    findings_by_id = {f.requirement_id: f for f in verification.findings} if verification else {}

    lines: list[str] = []
    lines.append(f"# {extraction.document_title}")
    lines.append("")
    if extraction.framework:
        lines.append(f"**Framework:** {extraction.framework}  ")
    lines.append(f"**Requirements extracted:** {len(extraction.requirements)}")
    lines.append("")

    if verification is not None:
        counts: dict[str, int] = {"pass": 0, "warning": 0, "fail": 0}
        for f in verification.findings:
            counts[f.status.value] += 1
        lines.append("## Verification summary")
        lines.append("")
        lines.append(
            f"- ✅ pass: **{counts['pass']}**  "
            f"⚠️  warning: **{counts['warning']}**  "
            f"❌ fail: **{counts['fail']}**"
        )
        lines.append(f"- Missed requirements flagged: **{len(verification.missed_requirements)}**")
        lines.append("")
        lines.append(f"_{verification.overall_summary}_")
        lines.append("")
        if verification.missed_requirements:
            lines.append("### Missed requirements")
            lines.append("")
            for missed in verification.missed_requirements:
                lines.append(f"- {missed}")
            lines.append("")

    if extraction.extraction_notes:
        lines.append("## Extraction notes")
        lines.append("")
        lines.append(f"> {extraction.extraction_notes}")
        lines.append("")

    by_category: dict[str, list[ComplianceRequirement]] = defaultdict(list)
    for req in extraction.requirements:
        by_category[req.category].append(req)

    severity_order = {
        Severity.critical: 0,
        Severity.high: 1,
        Severity.medium: 2,
        Severity.low: 3,
        Severity.informational: 4,
    }

    for category in sorted(by_category.keys()):
        lines.append(f"## {category.replace('_', ' ').title()}")
        lines.append("")
        for req in sorted(by_category[category], key=lambda r: severity_order[r.severity]):
            finding = findings_by_id.get(req.requirement_id)
            finding_md = None
            if finding is not None:
                badge = _STATUS_BADGE[finding.status]
                verbatim = "✓ verbatim quote" if finding.quote_verbatim else "✗ quote not verbatim"
                finding_md = f"**Verification:** {badge} — {verbatim}"
                if finding.issues:
                    finding_md += "\n\n" + "\n".join(f"- {issue}" for issue in finding.issues)
                if finding.suggested_fix:
                    finding_md += f"\n\n_Suggested fix: {finding.suggested_fix}_"
            lines.extend(_render_requirement(req, finding_md))

    return "\n".join(lines).rstrip() + "\n"


def _render_change(change: RequirementChange) -> list[str]:
    lines = [
        f"### {change.requirement_id} — {change.new.title}",
        "",
    ]
    if change.severity_shift:
        lines.append(f"**Severity:** {change.severity_shift}")
    lines.append(f"**Changed fields:** {_list(change.changed_fields)}")
    lines.append("")
    for field in change.changed_fields:
        old_value = getattr(change.old, field)
        new_value = getattr(change.new, field)
        lines.append(f"**`{field}`**")
        lines.append("")
        lines.append(f"- _old:_ {old_value!r}")
        lines.append(f"- _new:_ {new_value!r}")
        lines.append("")
    return lines


def render_diff_markdown(diff: DiffResult) -> str:
    lines = [
        "# Compliance diff",
        "",
        f"**Old:** {diff.old_document_title}  ",
        f"**New:** {diff.new_document_title}",
        "",
        f"- ➕ Added: **{len(diff.added)}**",
        f"- ➖ Removed: **{len(diff.removed)}**",
        f"- ✏️  Changed: **{len(diff.changed)}**",
        "",
    ]

    if not diff.has_changes:
        lines.append("_No requirement-level differences detected._")
        return "\n".join(lines) + "\n"

    if diff.added:
        lines.append("## Added")
        lines.append("")
        for req in diff.added:
            lines.extend(_render_requirement(req))

    if diff.removed:
        lines.append("## Removed")
        lines.append("")
        for req in diff.removed:
            lines.extend(_render_requirement(req))

    if diff.changed:
        lines.append("## Changed")
        lines.append("")
        for change in diff.changed:
            lines.extend(_render_change(change))

    return "\n".join(lines).rstrip() + "\n"
