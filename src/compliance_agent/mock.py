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
_ACME_V4_MARKER = "v4.0"


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


def _acme_v4_sample_requirements() -> list[ComplianceRequirement]:
    """v4.0 variant — tighter rotation, expanded MFA scope, longer retention,
    a new JIT privileged-access requirement, and a faster incident SLA. Useful
    as a diff target against the v3.2 baseline."""
    return [
        ComplianceRequirement(
            requirement_id="ACME-4.1",
            title="Provision production access through the identity provider",
            summary="All employee access to production systems must flow through Okta. Direct local accounts are forbidden except break-glass accounts, which must be vaulted and rotated within 12 hours of use.",
            source_quote="All employee access to production systems must be provisioned through the\nidentity provider (Okta). Direct local accounts on production hosts are\nprohibited except for break-glass accounts, which must be stored in the\ncorporate password vault and rotated within 12 hours of any use.",
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
            title="Quarterly access reviews with seven-year retention",
            summary="System owners must attest to each user's access at least once per calendar quarter. Review records must be retained for a minimum of seven years.",
            source_quote="Access reviews must be conducted at least once per calendar quarter. The\nsystem owner is responsible for attesting to the appropriateness of each\nuser's access. Reviews must be retained for a minimum of seven years.",
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
            title="Phishing-resistant MFA for all corporate systems",
            summary="MFA is mandatory for all access to corporate systems, regardless of whether they process customer data. SMS factors are prohibited; only TOTP, WebAuthn, or hardware security keys are acceptable.",
            source_quote="Multi-factor authentication is required for all access to corporate\nsystems, regardless of whether they process customer data. SMS-based MFA is\nnot permitted; only TOTP, WebAuthn, or hardware security keys are\nacceptable.",
            category="access_control",
            severity=Severity.critical,
            applies_to=["all corporate systems"],
            evidence_artifacts=[
                "IdP MFA enforcement policy",
                "MFA factor inventory excluding SMS",
                "hardware key issuance log",
            ],
            section_reference="Section 4.3",
        ),
        ComplianceRequirement(
            requirement_id="ACME-4.4",
            title="Just-in-time privileged access; no standing privilege",
            summary="Privileged access (root, sudo, administrator) to production systems must be brokered through a just-in-time access tool. Standing privileged access is prohibited.",
            source_quote="Privileged access (root, sudo, administrator) to production systems must\nbe brokered through a just-in-time access tool. Standing privileged access\nis prohibited.",
            category="access_control",
            severity=Severity.critical,
            applies_to=["privileged accounts on production systems"],
            evidence_artifacts=[
                "JIT access tool audit log",
                "standing-privilege exception register",
            ],
            section_reference="Section 4.4",
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
            title="30-minute internal / 72-hour customer incident notification",
            summary="Suspected unauthorized access to customer data must be reported to the Security team within 30 minutes of detection and to affected customers within 72 hours of confirmation.",
            source_quote="Security incidents involving suspected unauthorized access to customer\ndata must be reported to the Security team within 30 minutes of detection\nand to affected customers within 72 hours of confirmation.",
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

    Recognizes the bundled ACME samples (v3.2 / v4.0) and the bundled
    regulation excerpts (DPDP 2023, GDPR, HIPAA) and returns curated
    requirements for each. Any other input gets a generic 2-item stub.
    """
    if "DIGITAL PERSONAL DATA PROTECTION ACT" in document_text:
        return ExtractionResult(
            document_title="Digital Personal Data Protection Act, 2023 (India)",
            framework="DPDP Act 2023",
            requirements=_dpdp_2023_requirements(),
            extraction_notes="MOCK MODE — curated DPDP 2023 requirements. Run with --live for real extraction.",
        )

    if "CERT-IN CYBER SECURITY DIRECTIONS" in document_text:
        return ExtractionResult(
            document_title="CERT-In Cyber Security Directions, April 2022 (India)",
            framework="CERT-In 2022",
            requirements=_cert_in_2022_requirements(),
            extraction_notes="MOCK MODE — curated CERT-In 2022 requirements. Run with --live for real extraction.",
        )

    if "NIS2" in document_text or "DIRECTIVE (EU) 2022/2555" in document_text:
        return ExtractionResult(
            document_title="NIS2 Directive (EU) 2022/2555",
            framework="NIS2",
            requirements=_nis2_requirements(),
            extraction_notes="MOCK MODE — curated NIS2 requirements. Run with --live for real extraction.",
        )

    if "GENERAL DATA PROTECTION REGULATION" in document_text and "UK" not in document_text.splitlines()[0]:
        return ExtractionResult(
            document_title="General Data Protection Regulation (EU) 2016/679",
            framework="GDPR",
            requirements=_gdpr_requirements(),
            extraction_notes="MOCK MODE — curated GDPR requirements. Run with --live for real extraction.",
        )

    if "UK GDPR" in document_text and "DATA PROTECTION ACT 2018" in document_text:
        return ExtractionResult(
            document_title="UK GDPR and Data Protection Act 2018",
            framework="UK GDPR",
            requirements=_uk_gdpr_requirements(),
            extraction_notes="MOCK MODE — curated UK GDPR / DPA 2018 requirements. Run with --live for real extraction.",
        )

    if "CALIFORNIA CONSUMER PRIVACY ACT" in document_text:
        return ExtractionResult(
            document_title="California Consumer Privacy Act (CCPA / CPRA)",
            framework="CCPA",
            requirements=_ccpa_requirements(),
            extraction_notes="MOCK MODE — curated CCPA/CPRA requirements. Run with --live for real extraction.",
        )

    if "PCI DSS" in document_text:
        return ExtractionResult(
            document_title="PCI DSS v4.0",
            framework="PCI DSS v4.0",
            requirements=_pci_dss_requirements(),
            extraction_notes="MOCK MODE — curated PCI DSS v4.0 requirements. Run with --live for real extraction.",
        )

    if "UAE FEDERAL DECREE-LAW NO. 45" in document_text or "PERSONAL DATA PROTECTION LAW (PDPL)" in document_text:
        return ExtractionResult(
            document_title="UAE Federal Decree-Law No. 45 of 2021 (PDPL)",
            framework="UAE PDPL",
            requirements=_uae_pdpl_requirements(),
            extraction_notes="MOCK MODE — curated UAE PDPL 2021 requirements. Run with --live for real extraction.",
        )

    if "SINGAPORE PERSONAL DATA PROTECTION ACT" in document_text:
        return ExtractionResult(
            document_title="Singapore Personal Data Protection Act (PDPA)",
            framework="PDPA (SG)",
            requirements=_singapore_pdpa_requirements(),
            extraction_notes="MOCK MODE — curated Singapore PDPA requirements. Run with --live for real extraction.",
        )

    if "HIPAA" in document_text and "45 CFR" in document_text:
        return ExtractionResult(
            document_title="HIPAA (Privacy, Security, and Breach Notification Rules)",
            framework="HIPAA",
            requirements=_hipaa_requirements(),
            extraction_notes="MOCK MODE — curated HIPAA requirements. Run with --live for real extraction.",
        )

    if _ACME_MARKER in document_text and _ACME_V4_MARKER in document_text:
        return ExtractionResult(
            document_title="ACME Corp — Information Security Policy (v4.0)",
            framework=framework_hint or "Internal Policy",
            requirements=_acme_v4_sample_requirements(),
            extraction_notes="MOCK MODE — returned curated requirements for the bundled ACME v4.0 sample. Run with --live for real extraction.",
        )

    if _ACME_MARKER in document_text:
        return ExtractionResult(
            document_title="ACME Corp — Information Security Policy (v3.2)",
            framework=framework_hint or "Internal Policy",
            requirements=_acme_sample_requirements(),
            extraction_notes="MOCK MODE — returned curated requirements for the bundled ACME v3.2 sample. Run with --live for real extraction.",
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


def _dpdp_2023_requirements() -> list[ComplianceRequirement]:
    return [
        ComplianceRequirement(
            requirement_id="DPDP-S4",
            title="Lawful basis required for processing personal data",
            summary="A Data Fiduciary may process personal data only for a lawful purpose for which the Data Principal has given consent, or for a recognized 'legitimate use'.",
            source_quote="Personal data of a Data Principal may be processed only in accordance with this Act and for a lawful purpose for which the Data Principal has given her consent, or for certain legitimate uses.",
            category="lawful_basis",
            severity=Severity.critical,
            applies_to=["all data fiduciaries", "all processing of personal data"],
            evidence_artifacts=["record of processing activities", "lawful-basis register", "consent receipts"],
            section_reference="Section 4",
        ),
        ComplianceRequirement(
            requirement_id="DPDP-S5",
            title="Plain-language notice at the point of consent",
            summary="Every consent request must be accompanied by a notice in clear, plain language describing the data, the purpose, how to exercise rights, and how to complain to the Board.",
            source_quote="Every request made by a Data Fiduciary for consent shall be accompanied by a notice, in clear and plain language, containing the personal data being processed, the purpose, the manner in which the Data Principal may exercise her rights, and the manner of making a complaint to the Board.",
            category="transparency",
            severity=Severity.high,
            applies_to=["data fiduciaries collecting consent"],
            evidence_artifacts=["consent notice templates", "version history of notices", "translation log"],
            section_reference="Section 5",
        ),
        ComplianceRequirement(
            requirement_id="DPDP-S6",
            title="Consent must be free, specific, informed, and revocable",
            summary="Consent must be a clear affirmative action — free, specific, informed, unconditional and unambiguous — and Data Principals must be able to withdraw it at any time.",
            source_quote="The consent given by the Data Principal shall be free, specific, informed, unconditional and unambiguous, with a clear affirmative action. The Data Principal shall have the right to withdraw her consent at any time.",
            category="consent",
            severity=Severity.critical,
            applies_to=["all consent flows", "withdrawal mechanisms"],
            evidence_artifacts=["consent UX screenshots", "withdrawal endpoint logs", "consent revocation audit trail"],
            section_reference="Section 6",
        ),
        ComplianceRequirement(
            requirement_id="DPDP-S8",
            title="Reasonable security safeguards to prevent personal data breach",
            summary="Data Fiduciaries must implement technical and organisational measures and reasonable security safeguards, and must keep data accurate and complete when it drives decisions about Data Principals.",
            source_quote="A Data Fiduciary shall implement appropriate technical and organisational measures, and reasonable security safeguards to prevent personal data breach. The Data Fiduciary shall ensure the completeness, accuracy and consistency of personal data used to make decisions affecting the Data Principal.",
            category="security",
            severity=Severity.critical,
            applies_to=["all data fiduciaries", "decision-making systems using personal data"],
            evidence_artifacts=["security architecture review", "encryption inventory", "access logs", "data accuracy QA reports"],
            section_reference="Section 8",
        ),
        ComplianceRequirement(
            requirement_id="DPDP-S9",
            title="Verifiable parental consent and ban on targeting children",
            summary="Before processing a child's data, obtain verifiable parental/guardian consent. Tracking, behavioural monitoring, and targeted advertising aimed at children are prohibited.",
            source_quote="The Data Fiduciary shall, before processing any personal data of a child, obtain verifiable consent of the parent or lawful guardian. The Data Fiduciary shall not undertake tracking or behavioural monitoring of children or targeted advertising directed at children.",
            category="children",
            severity=Severity.critical,
            applies_to=["services accessible to or directed at children"],
            evidence_artifacts=["age-gating mechanism", "parental consent flow recordings", "ad-platform exclusion rules"],
            section_reference="Section 9",
        ),
        ComplianceRequirement(
            requirement_id="DPDP-S12",
            title="Right of access to processing summary and sharing list",
            summary="On request, the Data Fiduciary must give the Data Principal a summary of personal data being processed and the identities of all third parties with whom it has been shared.",
            source_quote="The Data Principal shall have the right to obtain a summary of personal data being processed, the identities of all Data Fiduciaries with whom the personal data has been shared, and any other information related to the processing.",
            category="data_subject_rights",
            severity=Severity.high,
            applies_to=["data subject access request workflows"],
            evidence_artifacts=["DSAR fulfilment SLA report", "sharing-recipient register"],
            section_reference="Section 12",
        ),
        ComplianceRequirement(
            requirement_id="DPDP-S13",
            title="Readily available grievance redressal",
            summary="A Data Fiduciary must provide readily available grievance redressal and respond within the prescribed period.",
            source_quote="The Data Principal shall have the right to readily available means of grievance redressal provided by the Data Fiduciary. The Data Fiduciary shall respond to grievances within the prescribed period.",
            category="grievance",
            severity=Severity.medium,
            applies_to=["customer-facing grievance channels"],
            evidence_artifacts=["grievance ticket SLA dashboard", "published grievance officer contact"],
            section_reference="Section 13",
        ),
        ComplianceRequirement(
            requirement_id="DPDP-S25",
            title="Penalties up to INR 250 crore for failed security safeguards",
            summary="The Data Protection Board may levy monetary penalties up to ₹250 crore for failure to take reasonable security safeguards that result in a personal data breach.",
            source_quote="The Board may impose monetary penalties up to two hundred and fifty crore rupees for failure to take reasonable security safeguards to prevent personal data breach.",
            category="penalties",
            severity=Severity.informational,
            applies_to=["enforcement context for all data fiduciaries"],
            evidence_artifacts=["board enforcement orders register"],
            section_reference="Section 25",
        ),
    ]


def _gdpr_requirements() -> list[ComplianceRequirement]:
    return [
        ComplianceRequirement(
            requirement_id="GDPR-Art5",
            title="Core processing principles",
            summary="All processing must be lawful, fair, transparent, purpose-limited, data-minimised, accurate, storage-limited, and secured with integrity and confidentiality.",
            source_quote="Personal data shall be: (a) processed lawfully, fairly and in a transparent manner; (b) collected for specified, explicit and legitimate purposes; (c) adequate, relevant and limited to what is necessary (data minimisation); (d) accurate and kept up to date; (e) kept in a form which permits identification for no longer than necessary; (f) processed in a manner that ensures appropriate security.",
            category="principles",
            severity=Severity.critical,
            applies_to=["all controllers and processors"],
            evidence_artifacts=["data inventory", "retention schedule", "ROPA (Article 30)"],
            section_reference="Article 5",
        ),
        ComplianceRequirement(
            requirement_id="GDPR-Art6",
            title="Establish a lawful basis before processing",
            summary="Processing requires at least one lawful basis: consent, contract, legal obligation, vital interests, public interest, or legitimate interests.",
            source_quote="Processing shall be lawful only if at least one of the following applies: consent of the data subject; necessity for performance of a contract; legal obligation; vital interests; public interest; or legitimate interests.",
            category="lawful_basis",
            severity=Severity.critical,
            applies_to=["every processing activity"],
            evidence_artifacts=["lawful-basis register per processing", "LIA documents for legitimate interest"],
            section_reference="Article 6",
        ),
        ComplianceRequirement(
            requirement_id="GDPR-Art13",
            title="Information notice at collection",
            summary="At the point of collection, the controller must provide the data subject with controller identity, purposes, legal basis, recipients, retention, and rights.",
            source_quote="The controller shall, at the time when personal data are obtained, provide the data subject with the identity of the controller, the purposes of processing, the legal basis, the recipients, retention period, and the rights of the data subject.",
            category="transparency",
            severity=Severity.high,
            applies_to=["all data collection touchpoints"],
            evidence_artifacts=["privacy notice versions", "layered notice UX", "just-in-time disclosures"],
            section_reference="Article 13",
        ),
        ComplianceRequirement(
            requirement_id="GDPR-Art17",
            title="Right to erasure ('right to be forgotten')",
            summary="Data subjects can require erasure without undue delay where data is no longer necessary, consent is withdrawn, or other specified grounds apply.",
            source_quote="The data subject shall have the right to obtain from the controller the erasure of personal data without undue delay where one of the specified grounds applies, including when the data are no longer necessary for the purposes for which they were collected.",
            category="data_subject_rights",
            severity=Severity.high,
            applies_to=["erasure request workflow", "downstream processors"],
            evidence_artifacts=["erasure SLA dashboard", "processor erasure attestations"],
            section_reference="Article 17",
        ),
        ComplianceRequirement(
            requirement_id="GDPR-Art25",
            title="Data protection by design and by default",
            summary="Implement appropriate technical and organisational measures at design time and during processing to enforce data-protection principles by default.",
            source_quote="The controller shall implement appropriate technical and organisational measures, both at the time of determination of the means for processing and at the time of the processing itself, designed to implement data protection principles in an effective manner.",
            category="privacy_by_design",
            severity=Severity.high,
            applies_to=["product and engineering teams", "system architecture"],
            evidence_artifacts=["DPbD design reviews", "default-private settings audit"],
            section_reference="Article 25",
        ),
        ComplianceRequirement(
            requirement_id="GDPR-Art32",
            title="Risk-appropriate security including encryption and resilience",
            summary="Both controllers and processors must implement security measures appropriate to the risk — including pseudonymisation, encryption, and the ability to restore data after an incident.",
            source_quote="The controller and processor shall implement appropriate technical and organisational measures to ensure a level of security appropriate to the risk, including pseudonymisation and encryption of personal data, and the ability to restore availability and access to personal data in a timely manner in the event of a physical or technical incident.",
            category="security",
            severity=Severity.critical,
            applies_to=["controllers", "processors"],
            evidence_artifacts=["encryption inventory", "DR test reports", "pseudonymisation design"],
            section_reference="Article 32",
        ),
        ComplianceRequirement(
            requirement_id="GDPR-Art33",
            title="72-hour breach notification to supervisory authority",
            summary="A personal-data breach must be notified to the supervisory authority without undue delay and not later than 72 hours after the controller becomes aware of it.",
            source_quote="In the case of a personal data breach, the controller shall without undue delay and, where feasible, not later than 72 hours after having become aware of it, notify the personal data breach to the supervisory authority.",
            category="incident_response",
            severity=Severity.critical,
            applies_to=["security incident response team", "DPO"],
            evidence_artifacts=["breach register", "supervisory-authority filings", "timeline reconstruction"],
            section_reference="Article 33",
        ),
        ComplianceRequirement(
            requirement_id="GDPR-Art35",
            title="DPIA for high-risk processing",
            summary="Where processing is likely to result in high risk to rights and freedoms, a Data Protection Impact Assessment must be performed prior to the processing.",
            source_quote="Where a type of processing is likely to result in a high risk to the rights and freedoms of natural persons, the controller shall, prior to the processing, carry out an assessment of the impact of the envisaged processing operations on the protection of personal data.",
            category="risk_assessment",
            severity=Severity.high,
            applies_to=["new high-risk processing initiatives"],
            evidence_artifacts=["DPIA register", "completed DPIA reports", "consultation records with DPO"],
            section_reference="Article 35",
        ),
    ]


def _hipaa_requirements() -> list[ComplianceRequirement]:
    return [
        ComplianceRequirement(
            requirement_id="HIPAA-164.502",
            title="Minimum-necessary use and disclosure of PHI",
            summary="Covered entities may not use or disclose PHI except as permitted, and must make reasonable efforts to limit it to the minimum necessary for the intended purpose.",
            source_quote="A covered entity may not use or disclose protected health information, except as permitted or required by this subpart. A covered entity must make reasonable efforts to limit protected health information to the minimum necessary to accomplish the intended purpose.",
            category="use_and_disclosure",
            severity=Severity.critical,
            applies_to=["covered entities", "workforce members handling PHI"],
            evidence_artifacts=["minimum-necessary policy", "role-based access matrices", "disclosure log"],
            section_reference="45 CFR 164.502",
        ),
        ComplianceRequirement(
            requirement_id="HIPAA-164.508",
            title="Written authorization for non-permitted uses",
            summary="Marketing uses, sale of PHI, and other non-permitted disclosures require valid written authorization from the individual.",
            source_quote="A covered entity must obtain an individual's authorization for any use or disclosure of protected health information that is not otherwise permitted or required by this subpart, including for marketing and the sale of protected health information.",
            category="authorization",
            severity=Severity.critical,
            applies_to=["marketing programs", "third-party data sales", "any non-treatment use"],
            evidence_artifacts=["authorization forms", "authorization audit trail"],
            section_reference="45 CFR 164.508",
        ),
        ComplianceRequirement(
            requirement_id="HIPAA-164.524",
            title="30-day right of access to PHI",
            summary="Individuals can inspect and obtain a copy of their PHI in a designated record set; the covered entity must act on the request within 30 days.",
            source_quote="An individual has a right of access to inspect and obtain a copy of protected health information in a designated record set. A covered entity must act on a request for access no later than 30 days after receipt.",
            category="patient_rights",
            severity=Severity.high,
            applies_to=["medical records / EHR teams", "patient-facing portals"],
            evidence_artifacts=["access request SLA dashboard", "fulfilment letters"],
            section_reference="45 CFR 164.524",
        ),
        ComplianceRequirement(
            requirement_id="HIPAA-164.308",
            title="Administrative safeguards including risk analysis",
            summary="Implement policies and procedures to prevent, detect, and correct security violations, including an accurate risk analysis, workforce security training, and a contingency plan.",
            source_quote="A covered entity must implement policies and procedures to prevent, detect, contain, and correct security violations, including conducting an accurate and thorough risk analysis, workforce security training, and a contingency plan for emergencies that damage systems containing electronic protected health information.",
            category="administrative_safeguards",
            severity=Severity.critical,
            applies_to=["all covered entities", "all workforce members"],
            evidence_artifacts=["risk analysis report", "training completion records", "contingency / DR plan"],
            section_reference="45 CFR 164.308",
        ),
        ComplianceRequirement(
            requirement_id="HIPAA-164.310",
            title="Physical safeguards for systems and facilities",
            summary="Restrict physical access to electronic information systems and the facilities housing them, while still allowing properly authorized access.",
            source_quote="A covered entity must implement policies and procedures to limit physical access to its electronic information systems and the facilities in which they are housed, while ensuring that properly authorized access is allowed.",
            category="physical_safeguards",
            severity=Severity.high,
            applies_to=["data centers", "device storage areas", "remote workforce equipment"],
            evidence_artifacts=["facility access logs", "device inventory", "workstation security policy"],
            section_reference="45 CFR 164.310",
        ),
        ComplianceRequirement(
            requirement_id="HIPAA-164.312",
            title="Technical safeguards: unique IDs, auto-logoff, encryption",
            summary="Restrict ePHI access to authorized persons via unique user IDs, automatic logoff, and encryption of electronic PHI.",
            source_quote="A covered entity must implement technical policies and procedures for electronic information systems that maintain electronic protected health information to allow access only to authorized persons. This includes unique user identification, automatic logoff, and encryption of electronic protected health information.",
            category="technical_safeguards",
            severity=Severity.critical,
            applies_to=["all systems storing or transmitting ePHI"],
            evidence_artifacts=["IdP user-ID policy", "session-timeout configuration", "encryption inventory"],
            section_reference="45 CFR 164.312",
        ),
        ComplianceRequirement(
            requirement_id="HIPAA-164.404",
            title="60-day individual breach notification",
            summary="Following discovery of a breach of unsecured PHI, notify each affected individual without unreasonable delay and no later than 60 days after discovery.",
            source_quote="A covered entity shall, following the discovery of a breach of unsecured protected health information, notify each individual whose information has been, or is reasonably believed to have been, accessed, acquired, used, or disclosed as a result of the breach. Notification shall be made without unreasonable delay and in no case later than 60 days after discovery.",
            category="breach_notification",
            severity=Severity.critical,
            applies_to=["incident response", "communications / legal"],
            evidence_artifacts=["breach notification letter templates", "delivery confirmation log"],
            section_reference="45 CFR 164.404",
        ),
        ComplianceRequirement(
            requirement_id="HIPAA-164.410",
            title="Business-associate breach reporting to covered entity",
            summary="A business associate must notify the covered entity of a breach of unsecured PHI without unreasonable delay and no later than 60 days after discovery.",
            source_quote="A business associate shall, following the discovery of a breach of unsecured protected health information, notify the covered entity of the breach without unreasonable delay and in no case later than 60 days after discovery.",
            category="breach_notification",
            severity=Severity.high,
            applies_to=["business associates", "vendor management"],
            evidence_artifacts=["BAA notification clause", "BA incident escalation log"],
            section_reference="45 CFR 164.410",
        ),
    ]


def _cert_in_2022_requirements() -> list[ComplianceRequirement]:
    return [
        ComplianceRequirement(
            requirement_id="CERTIN-D1",
            title="Synchronise all system clocks to NIC/NPL NTP servers",
            summary="All service providers, intermediaries, data centres, body corporates and Government organisations must sync ICT clocks to NIC or NPL NTP servers, or to NTP servers traceable to them.",
            source_quote="All service providers, intermediaries, data centres, body corporate and\nGovernment organisations shall connect to the Network Time Protocol (NTP)\nServer of the National Informatics Centre or the National Physical\nLaboratory, or to NTP servers traceable to these NTP servers, for\nsynchronisation of all their ICT systems clocks.",
            category="time_synchronization",
            severity=Severity.high,
            applies_to=["all ICT systems"],
            evidence_artifacts=["NTP configuration files", "time-sync drift monitoring dashboard"],
            section_reference="Direction (i)",
        ),
        ComplianceRequirement(
            requirement_id="CERTIN-D2",
            title="Report cyber incidents to CERT-In within 6 hours",
            summary="Any cyber incident, once noticed or brought to notice, must be reported to CERT-In within 6 hours.",
            source_quote="Any service provider, intermediary, data centre, body corporate and\nGovernment organisation shall mandatorily report cyber incidents to\nCERT-In within 6 hours of noticing such incidents or being brought to\nnotice about such incidents.",
            category="incident_response",
            severity=Severity.critical,
            applies_to=["security team", "designated CERT-In point of contact"],
            evidence_artifacts=["CERT-In incident-report submissions", "internal 6-hour SLA tracker"],
            section_reference="Direction (ii)",
        ),
        ComplianceRequirement(
            requirement_id="CERTIN-D4",
            title="Retain all ICT logs for 180 days within India",
            summary="Logs of all ICT systems must be enabled and securely maintained for a rolling 180 days, stored within Indian jurisdiction.",
            source_quote="All service providers, intermediaries, data centres, body corporate and\nGovernment organisations shall mandatorily enable logs of all their ICT\nsystems and maintain them securely for a rolling period of 180 days. The\nsame shall be maintained within the Indian jurisdiction.",
            category="logging",
            severity=Severity.high,
            applies_to=["all ICT systems", "log-storage infrastructure"],
            evidence_artifacts=["log retention policy", "log-storage region attestation", "log integrity checksums"],
            section_reference="Direction (iv)",
        ),
        ComplianceRequirement(
            requirement_id="CERTIN-D5",
            title="5-year KYC retention for VPS / VPN / cloud subscribers",
            summary="Data centres, VPS, cloud and VPN service providers must register accurate subscriber information and retain it for five years after registration ends.",
            source_quote="Data centres, Virtual Private Server (VPS) providers, Cloud Service\nproviders and Virtual Private Network Service (VPN Service) providers\nshall be required to register accurate information of subscribers /\ncustomers and to maintain it for a period of five years or longer after\ncancellation or withdrawal of the registration.",
            category="kyc",
            severity=Severity.high,
            applies_to=["data centre operators", "VPS providers", "cloud providers", "VPN providers"],
            evidence_artifacts=["KYC records", "retention policy with 5-year minimum"],
            section_reference="Direction (v)",
        ),
        ComplianceRequirement(
            requirement_id="CERTIN-D6",
            title="5-year KYC and transaction retention for virtual-asset providers",
            summary="Virtual-asset service providers, exchanges and custodian wallets must keep all KYC information and financial-transaction records for at least five years.",
            source_quote="Virtual asset service providers, virtual asset exchange providers and\ncustodian wallet providers shall mandatorily maintain all information\nobtained as part of Know Your Customer (KYC) and records of financial\ntransactions for a period of five years.",
            category="kyc",
            severity=Severity.high,
            applies_to=["virtual asset service providers", "exchanges", "custodian wallets"],
            evidence_artifacts=["KYC database", "transaction ledger with 5-year retention"],
            section_reference="Direction (vi)",
        ),
        ComplianceRequirement(
            requirement_id="CERTIN-D7",
            title="Designate a Point of Contact for CERT-In",
            summary="Each organisation must designate a Point of Contact to interface with CERT-In and share those details with CERT-In.",
            source_quote="Service providers, intermediaries, data centres, body corporate, and\nGovernment organisations shall designate a Point of Contact to interface\nwith CERT-In and shall communicate the details of the Point of Contact to\nCERT-In.",
            category="governance",
            severity=Severity.medium,
            applies_to=["security leadership"],
            evidence_artifacts=["PoC nomination letter to CERT-In", "internal escalation matrix"],
            section_reference="Direction (vii)",
        ),
    ]


def _nis2_requirements() -> list[ComplianceRequirement]:
    return [
        ComplianceRequirement(
            requirement_id="NIS2-Art20",
            title="Management body accountability and training",
            summary="Management bodies must approve cybersecurity risk-management measures, oversee their implementation, and undergo regular training. They can be held liable for infringements.",
            source_quote="Management bodies of essential and important entities shall approve the\ncybersecurity risk-management measures taken by those entities, oversee\ntheir implementation and can be held liable for infringements. Members of\nmanagement bodies shall be required to follow training, on a regular basis,\nto gain sufficient knowledge and skills to assess cybersecurity risks.",
            category="governance",
            severity=Severity.high,
            applies_to=["board of directors", "executive management"],
            evidence_artifacts=["board approval minutes", "executive cyber-training completion records"],
            section_reference="Article 20",
        ),
        ComplianceRequirement(
            requirement_id="NIS2-Art21",
            title="All-hazards cyber risk-management measures",
            summary="Implement appropriate, proportionate technical and organisational measures covering risk analysis, incident handling, business continuity, supply-chain security, vulnerability handling, cryptography, access control, MFA, and training.",
            source_quote="Essential and important entities shall take appropriate and proportionate\ntechnical, operational and organisational measures to manage the risks\nposed to the security of network and information systems. These measures\nshall include policies on risk analysis, incident handling, business\ncontinuity, supply chain security, security in acquisition, vulnerability\nhandling, basic cyber hygiene practices and cybersecurity training, use of\ncryptography and encryption, human resources security, access control,\nand multi-factor authentication.",
            category="risk_management",
            severity=Severity.critical,
            applies_to=["all essential and important entities"],
            evidence_artifacts=["ISMS documentation", "vendor security clauses", "BCP/DR plan", "MFA enforcement policy"],
            section_reference="Article 21",
        ),
        ComplianceRequirement(
            requirement_id="NIS2-Art23-ew",
            title="24-hour early warning of significant incidents",
            summary="An early warning must be submitted to the CSIRT or competent authority within 24 hours of becoming aware of a significant incident, including suspected malicious cause and cross-border impact.",
            source_quote="Essential and important entities shall notify, without undue delay, the\nCSIRT or, where applicable, the competent authority of any significant\nincident. An early warning shall be submitted within 24 hours of becoming\naware of the significant incident, indicating whether the incident is\nsuspected of being caused by unlawful or malicious acts or could have a\ncross-border impact.",
            category="incident_response",
            severity=Severity.critical,
            applies_to=["incident response team", "regulatory affairs"],
            evidence_artifacts=["CSIRT early-warning submission log", "internal 24-hour SLA tracker"],
            section_reference="Article 23",
        ),
        ComplianceRequirement(
            requirement_id="NIS2-Art23-not",
            title="72-hour detailed incident notification",
            summary="A detailed incident notification — initial assessment, severity, impact and indicators of compromise — must follow within 72 hours of becoming aware.",
            source_quote="A more detailed incident notification shall be submitted within 72 hours\nof becoming aware of the significant incident, including an initial\nassessment of the incident, its severity and impact, and where available\nthe indicators of compromise.",
            category="incident_response",
            severity=Severity.critical,
            applies_to=["incident response team"],
            evidence_artifacts=["72-hour notification documents", "incident-severity rubric"],
            section_reference="Article 23",
        ),
        ComplianceRequirement(
            requirement_id="NIS2-Art23-final",
            title="One-month final incident report",
            summary="A final report must be submitted no later than one month after the incident notification, with a full description, root cause, mitigations, and cross-border impact.",
            source_quote="A final report shall be submitted not later than one month after the\nsubmission of the incident notification, including a detailed description\nof the incident, the type of threat or root cause, applied and ongoing\nmitigation measures, and where applicable the cross-border impact.",
            category="incident_response",
            severity=Severity.high,
            applies_to=["incident response team", "post-incident review owners"],
            evidence_artifacts=["final report submissions", "root-cause analyses"],
            section_reference="Article 23",
        ),
        ComplianceRequirement(
            requirement_id="NIS2-Art24",
            title="Use of European cybersecurity certification schemes",
            summary="Member States may require entities to use ICT products, services or processes certified under European cybersecurity certification schemes.",
            source_quote="Member States may require essential and important entities to use\nparticular ICT products, ICT services and ICT processes that are\ncertified under European cybersecurity certification schemes.",
            category="procurement",
            severity=Severity.medium,
            applies_to=["procurement", "vendor management"],
            evidence_artifacts=["certification status of in-scope products", "procurement policy referencing EU schemes"],
            section_reference="Article 24",
        ),
    ]


def _ccpa_requirements() -> list[ComplianceRequirement]:
    return [
        ComplianceRequirement(
            requirement_id="CCPA-1798.100",
            title="Right to know personal information collected",
            summary="Consumers can request the categories and specific pieces of personal information a business has collected. Businesses must inform consumers of categories and purposes at or before collection.",
            source_quote="A consumer shall have the right to request that a business that collects\npersonal information about the consumer disclose to the consumer the\ncategories and specific pieces of personal information the business has\ncollected. A business shall, at or before the point of collection, inform\nconsumers of the categories of personal information to be collected and\nthe purposes for which the categories of personal information shall be\nused.",
            category="consumer_rights",
            severity=Severity.high,
            applies_to=["consumer-facing services in California"],
            evidence_artifacts=["data inventory", "at-collection notice", "right-to-know fulfilment SLA"],
            section_reference="§ 1798.100",
        ),
        ComplianceRequirement(
            requirement_id="CCPA-1798.105",
            title="Right to delete personal information",
            summary="On verifiable consumer request, businesses must delete the consumer's personal information and direct service providers and contractors to do the same.",
            source_quote="A consumer shall have the right to request that a business delete any\npersonal information about the consumer which the business has collected\nfrom the consumer. A business that receives a verifiable consumer request\nshall delete the consumer's personal information from its records and\ndirect any service providers and contractors to delete the consumer's\npersonal information from their records.",
            category="consumer_rights",
            severity=Severity.critical,
            applies_to=["primary data stores", "service providers / contractors"],
            evidence_artifacts=["deletion request log", "downstream attestations of deletion"],
            section_reference="§ 1798.105",
        ),
        ComplianceRequirement(
            requirement_id="CCPA-1798.106",
            title="Right to correct inaccurate personal information",
            summary="Consumers can request a business to correct inaccurate personal information it maintains, considering the nature of the data and the processing purpose.",
            source_quote="A consumer shall have the right to request a business that maintains\ninaccurate personal information about the consumer to correct that\ninaccurate personal information, taking into account the nature of the\npersonal information and the purposes of the processing.",
            category="consumer_rights",
            severity=Severity.high,
            applies_to=["customer service", "data stewards"],
            evidence_artifacts=["correction-request workflow", "data-quality audit trail"],
            section_reference="§ 1798.106",
        ),
        ComplianceRequirement(
            requirement_id="CCPA-1798.120",
            title="Right to opt-out of sale or sharing",
            summary="Consumers can opt out at any time of sale or sharing of their personal information. Businesses must provide a clear and conspicuous 'Do Not Sell or Share My Personal Information' link on their homepage.",
            source_quote="A consumer shall have the right, at any time, to direct a business that\nsells or shares personal information about the consumer to third parties\nnot to sell or share the consumer's personal information. A business that\nsells or shares personal information shall provide a clear and\nconspicuous link on its homepage titled \"Do Not Sell or Share My\nPersonal Information\".",
            category="opt_out",
            severity=Severity.critical,
            applies_to=["marketing", "advertising / ad-tech integrations"],
            evidence_artifacts=["homepage link screenshot", "opt-out signal handling docs (GPC)"],
            section_reference="§ 1798.120",
        ),
        ComplianceRequirement(
            requirement_id="CCPA-1798.121",
            title="Right to limit use of sensitive personal information",
            summary="Consumers can limit a business's use of sensitive personal information to only what is necessary to deliver the services or goods reasonably expected.",
            source_quote="A consumer shall have the right, at any time, to direct a business that\ncollects sensitive personal information about the consumer to limit its\nuse of the consumer's sensitive personal information to that use which is\nnecessary to perform the services or provide the goods reasonably\nexpected by an average consumer.",
            category="sensitive_data",
            severity=Severity.high,
            applies_to=["systems processing sensitive PI (precise geo, racial/ethnic origin, health, etc.)"],
            evidence_artifacts=["sensitive-PI use inventory", "'limit use' link and workflow"],
            section_reference="§ 1798.121",
        ),
        ComplianceRequirement(
            requirement_id="CCPA-1798.155",
            title="Civil penalties up to $7,500 per intentional violation",
            summary="A business or service provider that intentionally violates the CCPA can face civil penalties up to $7,500 per violation, with higher penalties for violations involving minors.",
            source_quote="A business or service provider that intentionally violates this title may\nbe liable for a civil penalty of up to seven thousand five hundred dollars\n($7,500) per violation. Violations involving minors may carry higher\npenalties.",
            category="penalties",
            severity=Severity.informational,
            applies_to=["enforcement context"],
            evidence_artifacts=["enforcement actions register"],
            section_reference="§ 1798.155",
        ),
    ]


def _pci_dss_requirements() -> list[ComplianceRequirement]:
    return [
        ComplianceRequirement(
            requirement_id="PCI-R1",
            title="Network security controls between trusted and untrusted networks",
            summary="Firewalls and other network security controls must be installed and maintained between trusted and untrusted networks; CDE traffic must be restricted to only what is necessary.",
            source_quote="Network security controls (NSCs), such as firewalls and other network\nsecurity technologies, shall be installed and maintained between trusted\nand untrusted networks. All inbound and outbound traffic to the cardholder\ndata environment shall be restricted to that which is necessary.",
            category="network_security",
            severity=Severity.critical,
            applies_to=["cardholder data environment (CDE) perimeter"],
            evidence_artifacts=["firewall ruleset", "quarterly ruleset review", "network diagram"],
            section_reference="Requirement 1",
        ),
        ComplianceRequirement(
            requirement_id="PCI-R2",
            title="No vendor defaults; documented secure configuration standards",
            summary="Vendor default accounts and passwords must be removed or disabled before deployment. Systems must follow documented hardening standards that address known vulnerabilities.",
            source_quote="Vendor default accounts and passwords shall be either removed or\ndisabled before installing a system on the network. All system components\nshall be configured securely, with documented configuration standards\naddressing known security vulnerabilities and consistent with industry\nhardening guidance.",
            category="secure_configuration",
            severity=Severity.high,
            applies_to=["all in-scope systems", "OS/database hardening"],
            evidence_artifacts=["hardening standards", "configuration scan reports"],
            section_reference="Requirement 2",
        ),
        ComplianceRequirement(
            requirement_id="PCI-R3",
            title="Strong cryptography for stored PAN; no SAD post-authorization",
            summary="Stored PAN must be rendered unreadable everywhere (e.g. strong cryptography with proper key management). Sensitive authentication data must not be retained after authorization.",
            source_quote="The storage of cardholder data shall be kept to a minimum. The primary\naccount number (PAN), when stored, shall be rendered unreadable anywhere\nit is stored — for example, by using strong cryptography with associated\nkey-management processes and procedures. Sensitive authentication data\nshall not be retained after authorization.",
            category="encryption",
            severity=Severity.critical,
            applies_to=["all systems storing PAN", "payment processing pipeline"],
            evidence_artifacts=["KMS configuration", "data-discovery scan results", "post-auth data-purge logs"],
            section_reference="Requirement 3",
        ),
        ComplianceRequirement(
            requirement_id="PCI-R4",
            title="Strong cryptography in transit over public networks",
            summary="Cardholder data sent over open, public networks must be protected with strong cryptography and security protocols, with trusted keys/certificates and only secure protocol versions.",
            source_quote="Strong cryptography and security protocols shall be used to safeguard\nsensitive cardholder data during transmission over open, public networks.\nTrusted keys and certificates shall be in place; the protocol in use must\nsupport only secure versions or configurations.",
            category="encryption",
            severity=Severity.critical,
            applies_to=["public-facing endpoints", "third-party integrations"],
            evidence_artifacts=["TLS configuration report", "certificate inventory"],
            section_reference="Requirement 4",
        ),
        ComplianceRequirement(
            requirement_id="PCI-R6",
            title="Secure development and timely patching",
            summary="Bespoke and custom software must be developed securely. Critical security patches must be installed within one month; other patches based on risk.",
            source_quote="Bespoke and custom software shall be developed securely. All system\ncomponents shall be protected from known vulnerabilities by installing\napplicable security patches. Critical patches shall be installed within\none month of release; other applicable patches within an appropriate\ntimeframe based on a risk-based approach.",
            category="vulnerability_management",
            severity=Severity.high,
            applies_to=["engineering / DevOps", "patch management"],
            evidence_artifacts=["SDLC documentation", "patch SLA dashboard", "vulnerability backlog"],
            section_reference="Requirement 6",
        ),
        ComplianceRequirement(
            requirement_id="PCI-R8",
            title="Unique IDs and MFA for CDE and all remote access",
            summary="Every user must have a unique ID. MFA is required for all access to the CDE and for all remote network access originating from outside the entity's network.",
            source_quote="All users shall be assigned a unique ID before access to system components\nor cardholder data is allowed. Multi-factor authentication shall be\nimplemented for all access into the cardholder data environment and for\nall remote network access originating from outside the entity's network.",
            category="access_control",
            severity=Severity.critical,
            applies_to=["CDE users", "remote workforce"],
            evidence_artifacts=["IdP unique-ID policy", "MFA enforcement screenshots"],
            section_reference="Requirement 8",
        ),
        ComplianceRequirement(
            requirement_id="PCI-R10",
            title="Audit logging with 12-month retention; daily review",
            summary="Audit logs must record all access to system components and cardholder data, retained at least 12 months (3 months immediately available). Logs must be reviewed daily for anomalies.",
            source_quote="Audit logs shall be implemented to record all access to system components\nand cardholder data. Audit log records shall be retained for at least 12\nmonths, with a minimum of 3 months immediately available for analysis.\nLogs shall be reviewed daily for anomalies and suspicious activity.",
            category="logging",
            severity=Severity.critical,
            applies_to=["SIEM operators", "all in-scope systems"],
            evidence_artifacts=["log retention configuration", "daily review checklist", "alerting rules"],
            section_reference="Requirement 10",
        ),
        ComplianceRequirement(
            requirement_id="PCI-R11",
            title="Quarterly vulnerability scans; annual penetration testing",
            summary="Internal and external vulnerability scans must be performed at least quarterly and after significant changes. Penetration tests must be performed at least annually and after major upgrades.",
            source_quote="Internal and external vulnerability scans shall be performed at least\nonce every three months and after any significant change. Penetration\ntesting shall be performed at least annually and after any significant\ninfrastructure or application upgrade or modification.",
            category="testing",
            severity=Severity.high,
            applies_to=["security testing", "release management"],
            evidence_artifacts=["quarterly ASV scan reports", "annual pentest report", "change-trigger scan records"],
            section_reference="Requirement 11",
        ),
    ]


def _uk_gdpr_requirements() -> list[ComplianceRequirement]:
    return [
        ComplianceRequirement(
            requirement_id="UKGDPR-Art5",
            title="Core processing principles",
            summary="Processing must be lawful, fair, transparent, purpose-limited, data-minimised, accurate, storage-limited, and protected by appropriate security.",
            source_quote="Personal data shall be: processed lawfully, fairly and in a transparent\nmanner; collected for specified, explicit and legitimate purposes;\nadequate, relevant and limited to what is necessary (data minimisation);\naccurate and kept up to date; kept in a form which permits identification\nfor no longer than necessary; processed in a manner that ensures\nappropriate security.",
            category="principles",
            severity=Severity.critical,
            applies_to=["all controllers and processors"],
            evidence_artifacts=["ROPA", "data inventory", "retention schedule"],
            section_reference="Article 5 (UK GDPR)",
        ),
        ComplianceRequirement(
            requirement_id="DPA2018-S9",
            title="Children's consent set at 13 for information society services",
            summary="In the UK, processing of a child's data under consent is lawful only if the child is at least 13; below that age, consent of the holder of parental responsibility is required.",
            source_quote="Where Article 6(1)(a) of the UK GDPR (consent) applies in relation to the\noffer of information society services directly to a child, in the United\nKingdom the processing of personal data of a child is lawful only if the\nchild is at least 13 years old. Where the child is below that age, such\nprocessing is lawful only if and to the extent that consent is given or\nauthorised by the holder of parental responsibility.",
            category="children",
            severity=Severity.high,
            applies_to=["services offered to UK children under 18"],
            evidence_artifacts=["age-gating UX", "parental consent flow records"],
            section_reference="Section 9 (DPA 2018)",
        ),
        ComplianceRequirement(
            requirement_id="UKGDPR-Art13",
            title="Information notice at point of collection",
            summary="At collection, controllers must provide identity, DPO contact, purposes, legal basis, recipients, retention, and rights — including the right to complain to the ICO.",
            source_quote="The controller shall, at the time when personal data are obtained, provide\nthe data subject with the identity of the controller, the contact details\nof the data protection officer where applicable, the purposes and legal\nbasis of processing, the recipients, retention periods, and the rights of\nthe data subject including the right to lodge a complaint with the\nInformation Commissioner.",
            category="transparency",
            severity=Severity.high,
            applies_to=["all collection touchpoints"],
            evidence_artifacts=["privacy notices (versioned)", "layered notice UX"],
            section_reference="Article 13 (UK GDPR)",
        ),
        ComplianceRequirement(
            requirement_id="UKGDPR-Art15",
            title="Right of access (DSAR)",
            summary="Individuals can confirm whether their data is being processed and get a copy plus information on purposes, categories, recipients, retention, and automated decision-making.",
            source_quote="The data subject shall have the right to obtain from the controller\nconfirmation as to whether or not personal data concerning him or her are\nbeing processed, and, where that is the case, access to the personal data\nand to information about the purposes of processing, categories of data,\nrecipients, retention, and the existence of automated decision-making.",
            category="data_subject_rights",
            severity=Severity.high,
            applies_to=["DSAR fulfilment workflow"],
            evidence_artifacts=["DSAR SLA dashboard", "DSAR template responses"],
            section_reference="Article 15 (UK GDPR)",
        ),
        ComplianceRequirement(
            requirement_id="UKGDPR-Art32",
            title="Appropriate security including encryption and resilience",
            summary="Controllers and processors must implement security appropriate to the risk, including pseudonymisation, encryption, and the ability to restore availability and access after an incident.",
            source_quote="The controller and the processor shall implement appropriate technical\nand organisational measures to ensure a level of security appropriate to\nthe risk, including pseudonymisation and encryption, the ability to\nensure ongoing confidentiality, integrity, availability and resilience of\nprocessing systems, and the ability to restore the availability of and\naccess to personal data in a timely manner.",
            category="security",
            severity=Severity.critical,
            applies_to=["controllers", "processors"],
            evidence_artifacts=["encryption inventory", "DR test reports"],
            section_reference="Article 32 (UK GDPR)",
        ),
        ComplianceRequirement(
            requirement_id="UKGDPR-Art33",
            title="72-hour breach notification to the ICO",
            summary="Personal-data breaches must be notified to the ICO without undue delay and within 72 hours of awareness, unless unlikely to risk individuals' rights and freedoms.",
            source_quote="In the case of a personal data breach, the controller shall without undue\ndelay and, where feasible, not later than 72 hours after having become\naware of it, notify the personal data breach to the Information\nCommissioner's Office, unless the breach is unlikely to result in a risk\nto the rights and freedoms of natural persons.",
            category="incident_response",
            severity=Severity.critical,
            applies_to=["incident response", "DPO"],
            evidence_artifacts=["ICO notifications", "breach register"],
            section_reference="Article 33 (UK GDPR)",
        ),
        ComplianceRequirement(
            requirement_id="DPA2018-S119A",
            title="Adhere to ICO Age-Appropriate Design Code",
            summary="Services likely to be accessed by children must follow the ICO's Age-Appropriate Design Code (defaults privacy-friendly, no nudge techniques, transparent terms in plain language).",
            source_quote="The Commissioner shall produce a code of practice which contains such\nguidance as the Commissioner considers appropriate on standards of age-\nappropriate design of relevant information society services which are\nlikely to be accessed by children.",
            category="children",
            severity=Severity.high,
            applies_to=["product/design teams of services likely to be accessed by UK children"],
            evidence_artifacts=["AADC self-assessment", "default-setting audit", "DPIA addressing AADC"],
            section_reference="Section 119A (DPA 2018)",
        ),
    ]


def _uae_pdpl_requirements() -> list[ComplianceRequirement]:
    return [
        ComplianceRequirement(
            requirement_id="UAE-Art4",
            title="Lawful bases for processing without consent",
            summary="Processing without the data subject's consent is allowed only in defined cases — public interest, legal obligations, contractual necessity, protection of the data subject, or preventive/occupational medicine.",
            source_quote="Personal data may be processed without the data subject's consent where\nprocessing is necessary to protect public interest, fulfill obligations\nunder existing laws, perform a contract to which the data subject is a\nparty, protect the data subject's interests, or for purposes of\npreventive or occupational medicine.",
            category="lawful_basis",
            severity=Severity.critical,
            applies_to=["all controllers"],
            evidence_artifacts=["lawful-basis register", "legal review memos"],
            section_reference="Article 4",
        ),
        ComplianceRequirement(
            requirement_id="UAE-Art6",
            title="Consent must be specific, clear, easy to access, and revocable",
            summary="Consent must be a specific, clear, simple, unambiguous and easy-to-access statement. The controller must be able to demonstrate consent and the data subject may withdraw at any time.",
            source_quote="Consent shall be a specific, clear, simple, unambiguous and easy-to-access\nstatement that the data subject agrees to the processing of his or her\npersonal data. The controller shall be able to demonstrate that the data\nsubject has consented. The data subject may withdraw consent at any time.",
            category="consent",
            severity=Severity.critical,
            applies_to=["all consent flows", "withdrawal endpoints"],
            evidence_artifacts=["consent UX screenshots", "consent receipts", "withdrawal audit log"],
            section_reference="Article 6",
        ),
        ComplianceRequirement(
            requirement_id="UAE-Art7",
            title="Controller security measures and personal-data record",
            summary="Controllers must take appropriate technical and organisational measures to protect personal data and maintain a special personal-data record available to the UAE Data Office on request.",
            source_quote="The controller shall take appropriate technical and organisational\nmeasures and apply appropriate standards and rules to protect personal\ndata. The controller shall maintain a special record of personal data and\nmake it available to the UAE Data Office on request.",
            category="security",
            severity=Severity.critical,
            applies_to=["all controllers"],
            evidence_artifacts=["personal-data record (RoPA-equivalent)", "security control inventory"],
            section_reference="Article 7",
        ),
        ComplianceRequirement(
            requirement_id="UAE-Art9",
            title="Bind processors with a contract and require sufficient guarantees",
            summary="Controllers may engage a processor only if it provides sufficient guarantees of compliance, and the engagement must be governed by a binding contract.",
            source_quote="The controller shall not engage a processor unless the processor provides\nsufficient guarantees that the processing shall be carried out in\naccordance with the provisions of this Decree-Law. Processing carried out\nby a processor shall be governed by a contract that binds the processor\nto the controller.",
            category="vendor_management",
            severity=Severity.high,
            applies_to=["vendor management", "procurement"],
            evidence_artifacts=["data processing agreements", "vendor security assessments"],
            section_reference="Article 9",
        ),
        ComplianceRequirement(
            requirement_id="UAE-Art13",
            title="Right to access processing information",
            summary="Data subjects have the right to obtain — without charge — the methods of processing, purposes, categories, recipients, retention periods, and information on cross-border transfers.",
            source_quote="The data subject shall have the right to obtain from the controller,\nwithout charge, the methods used in processing personal data, the\npurposes of processing, the categories of personal data being processed,\nthe recipients, the period of personal data retention, and information\nrelated to cross-border transfers.",
            category="data_subject_rights",
            severity=Severity.high,
            applies_to=["DSAR fulfilment workflow"],
            evidence_artifacts=["DSAR templates", "fulfilment SLA tracker"],
            section_reference="Article 13",
        ),
        ComplianceRequirement(
            requirement_id="UAE-Art21",
            title="Cross-border transfer requires adequacy, binding agreement, or consent",
            summary="Cross-border transfers are permitted to jurisdictions with adequate protection. Otherwise transfers require approved binding agreements, contractual clauses, or the data subject's express consent.",
            source_quote="Personal data may be transferred outside the State to jurisdictions that\nhave a special legislation on personal data protection providing an\nadequate level of protection. Transfers to jurisdictions without such\nlegislation shall be permitted only on the basis of approved binding\nagreements, contractual clauses or with the express consent of the data\nsubject.",
            category="cross_border_transfer",
            severity=Severity.critical,
            applies_to=["any export of personal data from the UAE"],
            evidence_artifacts=["transfer impact assessments", "SCCs/binding agreements", "explicit consent records"],
            section_reference="Article 21",
        ),
        ComplianceRequirement(
            requirement_id="UAE-Art23",
            title="Immediate breach notification to the UAE Data Office",
            summary="Personal-data breaches that would prejudice privacy, confidentiality or security must be notified to the UAE Data Office immediately upon awareness, with description and mitigations.",
            source_quote="The controller shall notify the UAE Data Office of any breach of personal\ndata immediately upon becoming aware of the breach, where the breach\nwould prejudice the privacy, confidentiality or security of the personal\ndata of the data subject. The notification shall include a description of\nthe breach and the measures taken.",
            category="incident_response",
            severity=Severity.critical,
            applies_to=["security incident response", "compliance"],
            evidence_artifacts=["breach notification log", "UAE Data Office submissions"],
            section_reference="Article 23",
        ),
    ]


def _singapore_pdpa_requirements() -> list[ComplianceRequirement]:
    return [
        ComplianceRequirement(
            requirement_id="SGPDPA-S13",
            title="Consent Obligation",
            summary="Organisations may not collect, use or disclose personal data unless the individual gives (or is deemed to give) informed consent for the specified purposes.",
            source_quote="An organisation shall not collect, use or disclose personal data about an\nindividual unless the individual gives, or is deemed to have given, his\nconsent under this Act to the collection, use or disclosure, as the case\nmay be. Consent is not validly given if the individual has not been\ninformed of the purposes.",
            category="consent",
            severity=Severity.critical,
            applies_to=["all collection points"],
            evidence_artifacts=["consent records", "consent notice content"],
            section_reference="Section 13",
        ),
        ComplianceRequirement(
            requirement_id="SGPDPA-S20",
            title="Notification Obligation",
            summary="Before or at the point of collection, organisations must inform individuals of the purposes for collection, use or disclosure, and provide a contact for questions on request.",
            source_quote="An organisation shall, on or before collecting personal data about an\nindividual, inform the individual of the purposes for the collection, use\nor disclosure of the personal data, and, on request, of the business\ncontact information of a person able to answer the individual's questions\nabout the collection, use or disclosure of the personal data.",
            category="transparency",
            severity=Severity.high,
            applies_to=["consumer-facing services", "marketing capture forms"],
            evidence_artifacts=["privacy notices", "DPO contact published"],
            section_reference="Section 20",
        ),
        ComplianceRequirement(
            requirement_id="SGPDPA-S21",
            title="Access and Correction Obligation",
            summary="On request, organisations must, as soon as reasonably possible, provide the individual their personal data and information on how it has been used/disclosed within the previous year.",
            source_quote="On request of an individual, an organisation shall, as soon as reasonably\npossible, provide the individual with personal data about the individual\nthat is in the possession or under the control of the organisation, and\ninformation about the ways in which the personal data may have been used\nor disclosed within a year before the date of the request.",
            category="data_subject_rights",
            severity=Severity.high,
            applies_to=["access request workflow"],
            evidence_artifacts=["access-request fulfilment log", "use/disclosure register"],
            section_reference="Section 21",
        ),
        ComplianceRequirement(
            requirement_id="SGPDPA-S24",
            title="Protection Obligation",
            summary="Organisations must protect personal data with reasonable security arrangements against unauthorised access, use, disclosure, copying, modification, disposal, or loss.",
            source_quote="An organisation shall protect personal data in its possession or under\nits control by making reasonable security arrangements to prevent\nunauthorised access, collection, use, disclosure, copying, modification,\ndisposal or similar risks, and the loss of any storage medium or device\non which personal data is stored.",
            category="security",
            severity=Severity.critical,
            applies_to=["all systems storing personal data"],
            evidence_artifacts=["security control inventory", "device encryption attestation"],
            section_reference="Section 24",
        ),
        ComplianceRequirement(
            requirement_id="SGPDPA-S25",
            title="Retention Limitation Obligation",
            summary="Organisations must cease to retain personal data, or anonymise it, once the original collection purpose is no longer served and retention is not necessary for legal or business reasons.",
            source_quote="An organisation shall cease to retain its documents containing personal\ndata, or remove the means by which the personal data can be associated\nwith particular individuals, as soon as it is reasonable to assume that\nthe purpose for which that personal data was collected is no longer being\nserved by retention and retention is no longer necessary for legal or\nbusiness purposes.",
            category="data_retention",
            severity=Severity.high,
            applies_to=["data lifecycle owners"],
            evidence_artifacts=["retention schedule", "purge job logs", "anonymisation runbooks"],
            section_reference="Section 25",
        ),
        ComplianceRequirement(
            requirement_id="SGPDPA-S26",
            title="Transfer Limitation Obligation",
            summary="Cross-border transfers are permitted only if the recipient provides a standard of protection comparable to the PDPA's.",
            source_quote="An organisation shall not transfer any personal data to a country or\nterritory outside Singapore except in accordance with requirements\nprescribed under this Act to ensure that the organisation provides a\nstandard of protection to personal data so transferred that is comparable\nto the protection under this Act.",
            category="cross_border_transfer",
            severity=Severity.critical,
            applies_to=["any export of personal data from Singapore"],
            evidence_artifacts=["transfer assessments", "binding corporate rules / contractual clauses"],
            section_reference="Section 26",
        ),
        ComplianceRequirement(
            requirement_id="SGPDPA-S26D",
            title="3-day Data Breach Notification Obligation",
            summary="Notifiable data breaches must be reported to the PDPC as soon as practicable and no later than 3 calendar days; affected individuals must be notified if significant harm is likely.",
            source_quote="Where an organisation has reason to believe that a notifiable data breach\nhas occurred, the organisation shall notify the Personal Data Protection\nCommission as soon as is practicable, but in any case no later than 3\ncalendar days after the day the organisation makes that assessment.\nAffected individuals shall also be notified if the breach is likely to\nresult in significant harm.",
            category="incident_response",
            severity=Severity.critical,
            applies_to=["incident response team", "DPO"],
            evidence_artifacts=["PDPC notifications log", "individual notification templates"],
            section_reference="Section 26D",
        ),
        ComplianceRequirement(
            requirement_id="SGPDPA-S11",
            title="Designate a Data Protection Officer",
            summary="Organisations must designate one or more individuals (a DPO) responsible for PDPA compliance and publicly publish at least one DPO's business contact information.",
            source_quote="An organisation shall designate one or more individuals to be responsible\nfor ensuring that the organisation complies with this Act. The business\ncontact information of at least one such individual shall be made\navailable to the public.",
            category="governance",
            severity=Severity.medium,
            applies_to=["all PDPA-scope organisations"],
            evidence_artifacts=["DPO appointment letter", "published DPO contact"],
            section_reference="Section 11",
        ),
    ]
