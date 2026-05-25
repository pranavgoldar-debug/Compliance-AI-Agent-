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

    if "GENERAL DATA PROTECTION REGULATION" in document_text:
        return ExtractionResult(
            document_title="General Data Protection Regulation (EU) 2016/679",
            framework="GDPR",
            requirements=_gdpr_requirements(),
            extraction_notes="MOCK MODE — curated GDPR requirements. Run with --live for real extraction.",
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
