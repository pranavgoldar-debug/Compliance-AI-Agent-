"""Stub extractor/verifier so the CLI runs without an Anthropic API key.

Returns hand-crafted output that matches the real schema. Swap to the live
extractor by passing `--live` to the CLI, or call `ComplianceExtractor` /
`ComplianceVerifier` from `extractor.py` / `verifier.py` directly.
"""
from __future__ import annotations

from compliance_agent.models import (
    ComplianceRequirement,
    ExtractionResult,
    FindingStatus,
    Severity,
    VerificationFinding,
    VerificationResult,
)
from compliance_agent.verifier import check_quote_verbatim


def mock_extract(document_text: str, *, framework_hint: str | None = None) -> ExtractionResult:
    """Return a stub extraction. Picks a couple of generic requirements so
    downstream code (CLI output, verification, JSON serialization) all work."""
    preview = document_text.strip().splitlines()[0] if document_text.strip() else "Untitled"
    return ExtractionResult(
        document_title=preview[:120],
        framework=framework_hint,
        requirements=[
            ComplianceRequirement(
                requirement_id="STUB-001",
                title="Placeholder access control requirement",
                summary=(
                    "Stub requirement returned because no Anthropic API key is configured. "
                    "Run with --live and ANTHROPIC_API_KEY set to extract real obligations."
                ),
                source_quote=document_text[:200],
                category="access_control",
                severity=Severity.medium,
                applies_to=["all employees"],
                evidence_artifacts=["access review logs"],
                section_reference=None,
            ),
            ComplianceRequirement(
                requirement_id="STUB-002",
                title="Placeholder data retention requirement",
                summary="Second stub requirement for shape verification.",
                source_quote=document_text[:200],
                category="data_retention",
                severity=Severity.low,
                applies_to=["customer data"],
                evidence_artifacts=["retention policy document"],
                section_reference=None,
            ),
        ],
        extraction_notes="MOCK MODE — no live model call was made. Set ANTHROPIC_API_KEY and re-run with --live for real extraction.",
    )


def mock_verify(source_text: str, extraction: ExtractionResult) -> VerificationResult:
    """Return a stub verification. Still runs the real verbatim-quote check
    (Python-only, no API call), so that signal is meaningful even in mock mode."""
    findings: list[VerificationFinding] = []
    for req in extraction.requirements:
        verbatim = check_quote_verbatim(source_text, req.source_quote)
        findings.append(
            VerificationFinding(
                requirement_id=req.requirement_id,
                status=FindingStatus.warning,
                quote_verbatim=verbatim,
                issues=["MOCK MODE — semantic verification skipped (no API call)."],
                suggested_fix=None,
            )
        )
    return VerificationResult(
        findings=findings,
        overall_summary="MOCK MODE — only Python-side verbatim-quote checks ran.",
        missed_requirements=[],
    )
