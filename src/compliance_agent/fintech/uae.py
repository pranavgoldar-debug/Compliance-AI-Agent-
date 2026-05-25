"""UAE filing catalog for a remittance fintech (CBUAE-licensed)."""
from __future__ import annotations

from compliance_agent.fintech import FintechFiling


def _build() -> list[FintechFiling]:
    return [
        # === Licensing & Authorization ===
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Stored Value Facility / Retail Payment Services",
            form_name="CBUAE Stored Value Facility (SVF) / Retail Payment Services and Card Schemes (RPSCS) licence",
            authority="Central Bank of the UAE (CBUAE)",
            frequency="One-time + Annual",
            due_date_rule="Authorization before commencement; annual confirmation of fitness & probity.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Free-zone (DIFC / ADGM)",
            form_name="DFSA / FSRA permission (Money Services, Operating an Exchange) — if licensed in DIFC/ADGM",
            authority="DFSA (DIFC) / FSRA (ADGM)",
            frequency="Annual",
            due_date_rule="Annual fees per regulator's schedule; ongoing reporting per Rulebook.",
            applicability="Conditional",
            applicability_note="Applies only if the entity is licensed in DIFC or ADGM rather than CBUAE onshore.",
        ),
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Prudential reporting",
            form_name="CBUAE regulatory returns (e.g. Form 19 / SVF returns)",
            authority="CBUAE",
            frequency="Monthly / Quarterly",
            due_date_rule="Per CBUAE supervisory reporting calendar — typically 15–30 days after period close.",
            applicability="Mandatory",
        ),

        # === AML / CFT ===
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="Suspicious Transaction Reporting",
            form_name="goAML STR / SAR submissions",
            authority="UAE Financial Intelligence Unit (FIU)",
            frequency="Event-based",
            due_date_rule="Without delay on forming suspicion.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="goAML reporting",
            form_name="goAML registration + AML/CFT Annual Report",
            authority="UAE FIU / Ministry of Economy",
            frequency="Annual",
            due_date_rule="Annual AML/CFT compliance report by the deadline set by the supervising authority (typically end Q1).",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="Sanctions",
            form_name="UAE local terrorist list & UN consolidated list screening + Executive Office reports",
            authority="Executive Office for Control & Non-Proliferation",
            frequency="Continuous + Event-based",
            due_date_rule="Continuous screening; freeze/report match within 24 hours of identification.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="UBO",
            form_name="UBO register filing with MoE / licensing authority",
            authority="Ministry of Economy / licensing authority",
            frequency="Event-based + Annual confirm",
            due_date_rule="Filing on incorporation; updates within 15 days of change; annual confirmation per licensing authority.",
            applicability="Mandatory",
        ),

        # === Data Protection ===
        FintechFiling(
            s_no=0,
            category="Data Protection & Privacy",
            area="Federal PDPL",
            form_name="UAE Federal PDPL (Decree-Law 45/2021) — consent records, DPO appointment (where applicable), breach notification",
            authority="UAE Data Office",
            frequency="Continuous + Event-based",
            due_date_rule="Breach notification immediately upon awareness where privacy/security/confidentiality of personal data is prejudiced.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Data Protection & Privacy",
            area="DIFC / ADGM",
            form_name="DIFC Data Protection Law 5/2020 / ADGM Data Protection Regulations 2021 — annual registration + DPO",
            authority="DIFC Commissioner of Data Protection / ADGM Office of Data Protection",
            frequency="Annual",
            due_date_rule="Annual registration on entity anniversary; ongoing compliance obligations.",
            applicability="Conditional",
            applicability_note="Applies only if the entity processes personal data in DIFC or ADGM.",
        ),

        # === Cybersecurity ===
        FintechFiling(
            s_no=0,
            category="Cybersecurity",
            area="National cyber",
            form_name="UAE Information Assurance Standards / NESA — annual self-assessment + incident reporting",
            authority="UAE Cybersecurity Council / TDRA",
            frequency="Annual + Event-based",
            due_date_rule="Annual self-assessment; major incident notification per sector regulator timelines.",
            applicability="Conditional",
        ),

        # === Tax ===
        FintechFiling(
            s_no=0,
            category="Direct Tax",
            area="Corporate Tax",
            form_name="UAE Corporate Tax registration + annual return (Federal Decree-Law 47/2022)",
            authority="Federal Tax Authority (FTA)",
            frequency="Annual",
            due_date_rule="Registration deadlines per FTA timetable; CT return within 9 months of FY close (15% domestic minimum top-up tax from 2025 for in-scope MNEs).",
            payment_due="9% CT on taxable income above AED 375,000; payment due same date as return (9 months from FY close). Late registration penalty AED 10,000.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Indirect Tax (VAT)",
            area="VAT",
            form_name="VAT return (Form VAT201)",
            authority="Federal Tax Authority",
            frequency="Monthly / Quarterly",
            due_date_rule="By the 28th of the month following the tax period.",
            payment_due="By the 28th of the month following the tax period.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Direct Tax",
            area="Economic Substance",
            form_name="Economic Substance Regulations (ESR) Notification + Annual Report",
            authority="Federal Tax Authority / MoF",
            frequency="Annual",
            due_date_rule="ESR Notification within 6 months of FY close; Annual ESR Report within 12 months of FY close.",
            applicability="Conditional",
            applicability_note="Applies to entities carrying on a 'Relevant Activity' (banking, insurance, fund management, headquarter, holding, IP, distribution & service centre, finance and leasing, shipping).",
        ),

        # === Corporate ===
        FintechFiling(
            s_no=0,
            category="Corporate & Statutory",
            area="Trade licence",
            form_name="Trade licence renewal (DED / free zone)",
            authority="Department of Economic Development / Free Zone authority",
            frequency="Annual",
            due_date_rule="On licence anniversary.",
            payment_due="Renewal fee typically AED 1,500–15,000 depending on activity and emirate / free zone; late-renewal penalty AED 250+/month.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Corporate & Statutory",
            area="Audited financials",
            form_name="Annual audited financial statements (CBUAE / FTA / DIFC / ADGM as applicable)",
            authority="Licensing authority + FTA",
            frequency="Annual",
            due_date_rule="Within 4–6 months of FY close per regulator/free-zone rules.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Labor & Payroll",
            area="WPS",
            form_name="Wages Protection System monthly salary file",
            authority="MOHRE",
            frequency="Monthly",
            due_date_rule="Salaries paid via WPS within 15 days of due date; monthly file submission per MOHRE.",
            payment_due="Same as salary disbursement.",
            applicability="Mandatory",
        ),
    ]


FILINGS = _build()
