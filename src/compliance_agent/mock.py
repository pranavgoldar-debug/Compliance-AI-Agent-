"""Stub extractor/verifier so the CLI runs without an Anthropic API key.

Returns hand-crafted output that matches the real schema. Swap to the live
extractor by passing `--live` to the CLI, or call `ComplianceExtractor` /
`ComplianceVerifier` from `extractor.py` / `verifier.py` directly.

The mock extractor recognizes the bundled ACME sample policy and returns a
realistic set of requirements for it. For any other input it returns a
generic 2-item stub.

The mock verifier runs only deterministic Python-side checks (no API):
verbatim quote, non-empty source_quote, non-empty evidence_artifacts,
non-empty applies_to. The semantic faithfulness pass is skipped.
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


_ACME_MARKER = "ACME CORP"


def _acme_sample_requirements() -> list[ComplianceRequirement]:
    return [
        ComplianceRequirement(
            requirement_id="ACME-4.1",
            title="Provision production access through the identity provider",
            summary="All employee access to production systems must flow through Okta. Direct local accounts are forbidden except break-glass accounts, which must be vaulted and rotated within 24 hours of use.",
            source_quote="All employee access to production systems must be provisioned through the\nidentity provider (Okta). Direct local accounts on production hosts are\nprohibited except for break-glass accounts, which must be stored in the\ncorporate password vault and rotated within 24 hours of any use.",
            category="access_control",
            severity=Severity.high,
            applies_to=["production systems", "break-glass accounts"],
            evidence_artifacts=[
                "Okta provisioning logs",
                "break-glass vault audit trail",
                "rotation timestamps",
            ],
            section_reference="Section 4.1",
        ),
        ComplianceRequirement(
            requirement_id="ACME-4.2",
            title="Quarterly access reviews with three-year retention",
            summary="System owners must attest to each user's access at least once per calendar quarter. Review records must be retained for a minimum of three years.",
            source_quote="Access reviews must be conducted at least once per calendar quarter. The\nsystem owner is responsible for attesting to the appropriateness of each\nuser's access. Reviews must be retained for a minimum of three years.",
            category="access_control",
            severity=Severity.medium,
            applies_to=["system owners", "all users with system access"],
            evidence_artifacts=[
                "quarterly access review reports",
                "owner attestation signatures",
                "retention archive",
            ],
            section_reference="Section 4.2",
        ),
        ComplianceRequirement(
            requirement_id="ACME-4.3",
            title="Phishing-resistant MFA for customer-data systems",
            summary="MFA is mandatory for all access to systems processing customer data. SMS factors are prohibited; only TOTP or WebAuthn are acceptable.",
            source_quote="Multi-factor authentication is required for all access to systems\nprocessing customer data. SMS-based MFA is not permitted; only TOTP or\nWebAuthn factors are acceptable.",
            category="access_control",
            severity=Severity.critical,
            applies_to=["systems processing customer data"],
            evidence_artifacts=[
                "IdP MFA enforcement policy",
                "MFA factor inventory excluding SMS",
            ],
            section_reference="Section 4.3",
        ),
        ComplianceRequirement(
            requirement_id="ACME-5.1",
            title="30-day customer data deletion after account closure",
            summary="Customer personal data must be deleted within 30 days of account closure. Legally required retention (e.g. tax records — 7 years) is exempt.",
            source_quote="Customer personal data must be deleted within 30 days of account closure,\nexcept where retention is required by law (e.g. tax records, which are\nretained for seven years).",
            category="data_retention",
            severity=Severity.high,
            applies_to=["customer personal data"],
            evidence_artifacts=[
                "deletion job logs",
                "account-closure-to-deletion timing report",
                "legal hold register",
            ],
            section_reference="Section 5.1",
        ),
        ComplianceRequirement(
            requirement_id="ACME-5.2",
            title="AES-256 backup encryption with contractual data residency",
            summary="Backups containing personal data must be encrypted at rest with AES-256 or stronger and stored in regions matching customer contractual data residency requirements.",
            source_quote="Backups containing personal data must be encrypted at rest using AES-256\nor stronger and stored in a region that complies with the customer's\ncontractual data residency requirements.",
            category="encryption",
            severity=Severity.critical,
            applies_to=["backups containing personal data"],
            evidence_artifacts=[
                "KMS key configuration",
                "backup region inventory",
                "customer residency contract clauses",
            ],
            section_reference="Section 5.2",
        ),
        ComplianceRequirement(
            requirement_id="ACME-6.1",
            title="1-hour internal / 72-hour customer incident notification",
            summary="Suspected unauthorized access to customer data must be reported to the Security team within 1 hour of detection and to affected customers within 72 hours of confirmation.",
            source_quote="Security incidents involving suspected unauthorized access to customer\ndata must be reported to the Security team within 1 hour of detection and\nto affected customers within 72 hours of confirmation.",
            category="incident_response",
            severity=Severity.critical,
            applies_to=["security team", "affected customers"],
            evidence_artifacts=[
                "incident ticket timestamps",
                "customer notification log",
            ],
            section_reference="Section 6.1",
        ),
        ComplianceRequirement(
            requirement_id="ACME-6.2",
            title="Post-incident review within 10 business days",
            summary="Every incident requires a post-incident review within 10 business days of closure, with findings and remediation owners tracked in the incident management system.",
            source_quote="A post-incident review must be conducted within 10 business days of\nincident closure. Findings and remediation owners are tracked in the\nincident management system.",
            category="incident_response",
            severity=Severity.medium,
            applies_to=["incident response team"],
            evidence_artifacts=[
                "post-incident review documents",
                "remediation tracking entries",
            ],
            section_reference="Section 6.2",
        ),
    ]


def mock_extract(document_text: str, *, framework_hint: str | None = None) -> ExtractionResult:
    """Return a stub extraction.

    When the input is the bundled ACME sample policy, returns 7 realistic
    requirements covering access control, retention, encryption, and incident
    response. For any other input, returns a generic 2-item stub so downstream
    code paths still exercise correctly.
    """
    if _ACME_MARKER in document_text:
        return ExtractionResult(
            document_title="ACME Corp — Information Security Policy (v3.2)",
            framework=framework_hint or "Internal Policy",
            requirements=_acme_sample_requirements(),
            extraction_notes="MOCK MODE — returned curated requirements for the bundled ACME sample. Run with --live for real extraction.",
        )

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


def _deterministic_checks(
    source_text: str, requirement: ComplianceRequirement
) -> tuple[bool, list[str]]:
    """Run Python-only sanity checks on a requirement. Returns (verbatim, issues)."""
    issues: list[str] = []
    verbatim = check_quote_verbatim(source_text, requirement.source_quote)

    if not requirement.source_quote.strip():
        issues.append("`source_quote` is empty.")
    elif not verbatim:
        issues.append("`source_quote` is not a verbatim substring of the source document.")

    if not requirement.evidence_artifacts:
        issues.append("`evidence_artifacts` is empty — no concrete artifacts to audit against.")

    if not requirement.applies_to:
        issues.append("`applies_to` is empty — scope is undefined.")

    if not requirement.summary.strip():
        issues.append("`summary` is empty.")

    if not requirement.title.strip():
        issues.append("`title` is empty.")

    return verbatim, issues


def mock_verify(source_text: str, extraction: ExtractionResult) -> VerificationResult:
    """Return a deterministic verification using Python-only checks.

    No model call. Each requirement gets:
      - quote_verbatim — real substring check
      - status:
          pass    — all Python checks succeed
          warning — one or more sanity-check defects
          fail    — never produced in mock mode (semantic checks are skipped)
    """
    findings: list[VerificationFinding] = []
    pass_count = 0
    warning_count = 0

    for req in extraction.requirements:
        verbatim, issues = _deterministic_checks(source_text, req)
        if issues:
            status = FindingStatus.warning
            warning_count += 1
        else:
            status = FindingStatus.pass_
            pass_count += 1

        findings.append(
            VerificationFinding(
                requirement_id=req.requirement_id,
                status=status,
                quote_verbatim=verbatim,
                issues=issues,
                suggested_fix=None,
            )
        )

    summary = (
        f"MOCK MODE — Python-only checks: pass={pass_count}, warning={warning_count}. "
        "Semantic faithfulness, severity calibration, and missed-requirements detection "
        "require --live."
    )
    return VerificationResult(
        findings=findings,
        overall_summary=summary,
        missed_requirements=[],
    )
