"""UK filing catalog for a remittance fintech (FCA Authorised Payment Institution)."""
from __future__ import annotations

from compliance_agent.fintech import FintechFiling


def _build() -> list[FintechFiling]:
    return [
        # === Licensing & Authorization ===
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Payment Services",
            form_name="FCA Authorised Payment Institution permission (PSR 2017) + ongoing change-in-control notifications",
            authority="FCA",
            frequency="One-time + Event-based",
            due_date_rule="Authorization before commencement; change-in-control notification before completion of change.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Regulatory reporting",
            form_name="FCA Regulatory Returns (FSA056 / REP017 etc.) via GABRIEL/RegData",
            authority="FCA",
            frequency="Monthly / Quarterly / Annual",
            due_date_rule="Per RegData schedule for each return — typically 15–30 business days after period close.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Safeguarding",
            form_name="Annual safeguarding audit + monthly safeguarding reconciliation",
            authority="FCA",
            frequency="Annual + Monthly",
            due_date_rule="Annual audit within 4 months of FY close; safeguarding reconciliation as often as accounting records are produced.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Senior Managers & Certification Regime",
            form_name="SMCR Form A (approvals), Conduct Rules training, annual certification",
            authority="FCA",
            frequency="Annual + Event-based",
            due_date_rule="Approvals before role start; annual certification at least once every 12 months.",
            applicability="Mandatory",
        ),

        # === AML / CFT ===
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="Suspicious Activity Reports",
            form_name="SAR / DAML submissions to NCA via SAR Online",
            authority="National Crime Agency (NCA)",
            frequency="Event-based",
            due_date_rule="As soon as practicable after suspicion forms; DAML (defence) before proceeding with the transaction.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="MLR 2017",
            form_name="Annual MLRO report + business-wide risk assessment refresh",
            authority="Internal + FCA on request",
            frequency="Annual",
            due_date_rule="Within 90 days of FY close.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="Sanctions",
            form_name="OFSI consolidated sanctions list screening + reports of breaches/frozen funds",
            authority="OFSI (HM Treasury)",
            frequency="Continuous + Event-based + Annual",
            due_date_rule="Screening on every transaction; breach reports as soon as practicable; annual frozen-funds report by deadline OFSI sets each year.",
            applicability="Mandatory",
        ),

        # === Consumer Protection ===
        FintechFiling(
            s_no=0,
            category="Consumer Protection",
            area="Consumer Duty",
            form_name="FCA Consumer Duty — annual board attestation + outcomes monitoring",
            authority="FCA",
            frequency="Annual",
            due_date_rule="Annual board review and attestation within 12 months of last (first by 31 Jul 2024).",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Consumer Protection",
            area="Complaints",
            form_name="DISP complaints return + Financial Ombudsman cooperation",
            authority="FCA / Financial Ombudsman Service",
            frequency="Half-Yearly",
            due_date_rule="30 business days after each reporting period (DISP 1 Annex 1).",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Consumer Protection",
            area="APP fraud reimbursement",
            form_name="PSR Authorised Push Payment Fraud reimbursement — data reporting",
            authority="PSR / Pay.UK",
            frequency="Monthly / Quarterly",
            due_date_rule="Per PSR mandatory reimbursement scheme (effective Oct 2024) — data submissions on the PSR schedule.",
            applicability="Conditional",
            applicability_note="Applies to Faster Payments and CHAPS participants serving consumers in the UK.",
        ),

        # === Data Protection ===
        FintechFiling(
            s_no=0,
            category="Data Protection & Privacy",
            area="UK GDPR / DPA 2018",
            form_name="UK GDPR + DPA 2018 — ICO registration, DPO contact, ROPA, 72h breach reports",
            authority="Information Commissioner's Office (ICO)",
            frequency="Annual + Continuous + Event-based",
            due_date_rule="ICO data-protection fee paid annually on anniversary; breach to ICO within 72 hours of awareness.",
            payment_due="Annual ICO fee on anniversary.",
            applicability="Mandatory",
        ),

        # === Cybersecurity ===
        FintechFiling(
            s_no=0,
            category="Cybersecurity",
            area="Operational resilience",
            form_name="FCA / Bank of England Operational Resilience policy — important business services & impact tolerances",
            authority="FCA",
            frequency="Continuous + Annual review",
            due_date_rule="Self-assessment maintained; full operational-resilience compliance by 31 Mar 2025.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Cybersecurity",
            area="Incident reporting",
            form_name="FCA Principle 11 incident notifications + REP018 operational/security incident reporting",
            authority="FCA",
            frequency="Event-based",
            due_date_rule="As soon as reasonably practicable on becoming aware of a material incident.",
            applicability="Mandatory",
        ),

        # === Tax ===
        FintechFiling(
            s_no=0,
            category="Direct Tax",
            area="Corporation Tax",
            form_name="CT600 + iXBRL accounts + Corporation Tax payment",
            authority="HMRC",
            frequency="Annual + Quarterly (large)",
            due_date_rule="CT600 within 12 months of FY close; CT payment within 9 months & 1 day (large companies on quarterly instalments).",
            payment_due="9 months and 1 day after FY close (or per QIP).",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Indirect Tax (VAT)",
            area="VAT",
            form_name="VAT return (Making Tax Digital)",
            authority="HMRC",
            frequency="Quarterly",
            due_date_rule="Filing + payment within 1 month and 7 days after VAT-quarter close.",
            payment_due="Same date as filing.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Labor & Payroll",
            area="PAYE",
            form_name="PAYE / NIC RTI submissions (FPS / EPS) + P11D",
            authority="HMRC",
            frequency="Monthly + Annual",
            due_date_rule="FPS on or before each payday; P11D for benefits by 6 Jul; PAYE settlement payments per HMRC schedule.",
            payment_due="By the 22nd of the following month (electronic).",
            applicability="Mandatory",
        ),

        # === Corporate ===
        FintechFiling(
            s_no=0,
            category="Corporate & Statutory",
            area="Companies House",
            form_name="Confirmation Statement (CS01) + Annual Accounts + PSC register updates",
            authority="Companies House",
            frequency="Annual + Event-based",
            due_date_rule="Confirmation Statement within 14 days of review date; accounts within 9 months of FY close; PSC updates within 14 days of internal record and 14 days more to register.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Corporate & Statutory",
            area="ECCT 2023",
            form_name="Economic Crime and Corporate Transparency Act — identity verification, ACSP registration",
            authority="Companies House",
            frequency="Continuous + Event-based",
            due_date_rule="Per Companies House phased implementation through 2024–2026.",
            applicability="Mandatory",
        ),
    ]


FILINGS = _build()
