"""Singapore filing catalog for a remittance fintech (MAS Payment Services Act licensee)."""
from __future__ import annotations

from compliance_agent.fintech import FintechFiling


def _build() -> list[FintechFiling]:
    return [
        # === Licensing & Authorization ===
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Payment Services Act",
            form_name="MAS PS Act licence (Money-changing / Standard / Major Payment Institution) — ongoing conditions",
            authority="Monetary Authority of Singapore (MAS)",
            frequency="One-time + Continuous",
            due_date_rule="Authorization before commencement; safeguarding and base-capital tested continuously.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Prudential reporting",
            form_name="MAS PS-N02 — periodic returns (transaction volumes, safeguarding)",
            authority="MAS",
            frequency="Half-Yearly / Annual",
            due_date_rule="As prescribed in PS-N02 — typically 21 days after period close for half-year returns.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Audit",
            form_name="Annual auditor's report + safeguarding audit (PS Act)",
            authority="MAS",
            frequency="Annual",
            due_date_rule="Within 5 months of FY close.",
            applicability="Mandatory",
        ),

        # === AML / CFT ===
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="Suspicious Transaction Reporting",
            form_name="STR filing to STRO via SONAR",
            authority="Suspicious Transaction Reporting Office (STRO)",
            frequency="Event-based",
            due_date_rule="Promptly upon forming knowledge or suspicion.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="MAS AML/CFT Notices",
            form_name="MAS Notice PSN01 / PSN02 — AML/CFT obligations (CDD, screening, recordkeeping)",
            authority="MAS",
            frequency="Continuous",
            due_date_rule="Continuous CDD on onboarding and ongoing monitoring; CTR-equivalent retention for 5 years.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="Targeted financial sanctions",
            form_name="MAS / UN sanctions screening + freeze reports",
            authority="MAS",
            frequency="Continuous + Event-based",
            due_date_rule="Continuous screening; immediate freezing and reporting to MAS on positive match.",
            applicability="Mandatory",
        ),

        # === Data Protection ===
        FintechFiling(
            s_no=0,
            category="Data Protection & Privacy",
            area="PDPA",
            form_name="Singapore PDPA — DPO appointment, consent obligations, 3-day breach notification",
            authority="Personal Data Protection Commission (PDPC)",
            frequency="Continuous + Event-based",
            due_date_rule="Notifiable breach to PDPC no later than 3 calendar days after assessment; affected individuals notified if likely significant harm.",
            applicability="Mandatory",
        ),

        # === Cybersecurity ===
        FintechFiling(
            s_no=0,
            category="Cybersecurity",
            area="MAS Cyber Hygiene",
            form_name="MAS Notice PSN06 / TRM Guidelines — Cyber Hygiene baseline + Technology Risk Management",
            authority="MAS",
            frequency="Continuous + Annual review",
            due_date_rule="Baseline controls continuously enforced; TRM self-assessment per MAS expectations.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Cybersecurity",
            area="Incident reporting",
            form_name="MAS Notice 644 / PSN06 — incident notification (1-hour relevant incidents)",
            authority="MAS",
            frequency="Event-based",
            due_date_rule="Within 1 hour upon discovery of a 'relevant incident'; root-cause analysis within 14 days.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Cybersecurity",
            area="Outsourcing",
            form_name="MAS Guidelines on Outsourcing — register of outsourcing arrangements + notification of material outsourcing",
            authority="MAS",
            frequency="Continuous + Event-based",
            due_date_rule="Register maintained continuously; pre-engagement notification for material outsourcing.",
            applicability="Mandatory",
        ),

        # === Tax ===
        FintechFiling(
            s_no=0,
            category="Indirect Tax (GST)",
            area="GST",
            form_name="GST Form 5",
            authority="IRAS",
            frequency="Quarterly",
            due_date_rule="By 30 days after end of accounting period (electronic filing).",
            payment_due="Same as filing.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Direct Tax",
            area="Corporate Income Tax",
            form_name="Form C / C-S + ECI (Estimated Chargeable Income)",
            authority="IRAS",
            frequency="Annual",
            due_date_rule="ECI within 3 months of FY close; Form C / C-S by 30 Nov.",
            payment_due="Per IRAS instalment plan or upon NoA.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Labor & Payroll",
            area="CPF",
            form_name="CPF monthly contribution + IR8A annual return of employee earnings",
            authority="CPF Board / IRAS",
            frequency="Monthly + Annual",
            due_date_rule="CPF by 14th of following month; IR8A by 1 Mar.",
            payment_due="CPF by 14th of following month.",
            applicability="Mandatory",
        ),

        # === Corporate ===
        FintechFiling(
            s_no=0,
            category="Corporate & Statutory",
            area="ACRA",
            form_name="Annual Return (ACRA) + AGM (where applicable)",
            authority="ACRA",
            frequency="Annual",
            due_date_rule="Annual Return within 7 months of FY close (private company); AGM within 6 months of FY close.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Corporate & Statutory",
            area="Register of Controllers",
            form_name="Register of Registrable Controllers + ACRA notifications",
            authority="ACRA",
            frequency="Event-based",
            due_date_rule="Updates within 2 business days of becoming aware of change; ACRA filings within 2 business days of update.",
            applicability="Mandatory",
        ),
    ]


FILINGS = _build()
