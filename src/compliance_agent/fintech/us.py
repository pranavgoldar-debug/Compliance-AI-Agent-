"""US filing catalog for a remittance fintech (MSB).

Money transmission is state-licensed in the US; federal AML registration
is with FinCEN. State-by-state licensing is not enumerated here — it is
captured as a single tracked item.
"""
from __future__ import annotations

from compliance_agent.fintech import FintechFiling


def _build() -> list[FintechFiling]:
    return [
        # === Licensing & Authorization ===
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Federal MSB registration",
            form_name="FinCEN Form 107 — MSB registration / renewal",
            authority="FinCEN",
            frequency="Bi-annual (every 2 years)",
            due_date_rule="Initial registration within 180 days of establishment; renewal by 31 Dec of every other calendar year.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="State money transmitter licences",
            form_name="State Money Transmitter Licenses (NMLS) — annual renewals + quarterly call reports",
            authority="State financial regulators via NMLS (CSBS)",
            frequency="Annual + Quarterly (MSB Call Report)",
            due_date_rule="State licence renewals by 31 Dec; MSB Call Report within 45 days of quarter close.",
            payment_due="Per-state renewal fees range ~$500–$5,000/state. Initial licensing $1,000–$100,000+ per state plus surety bond $25k–$2M.",
            applicability="Mandatory",
            applicability_note="Required in every US state where the entity transmits money; tracked per-state in NMLS.",
        ),
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Surety bonds / net worth",
            form_name="Per-state surety bond + minimum net worth confirmation",
            authority="State financial regulators",
            frequency="Annual",
            due_date_rule="Per state schedule — typically alongside licence renewal.",
            applicability="Mandatory",
        ),

        # === AML / CFT ===
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="Suspicious Activity Reports",
            form_name="FinCEN SAR (Form 111)",
            authority="FinCEN",
            frequency="Event-based",
            due_date_rule="Within 30 calendar days of initial detection (60 days if subject is unidentified).",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="Currency Transaction Reports",
            form_name="FinCEN CTR (Form 112)",
            authority="FinCEN",
            frequency="Event-based",
            due_date_rule="Within 15 calendar days of transaction (25 if filed electronically) — currency transactions > $10,000.",
            applicability="Conditional",
            applicability_note="Triggered by cash transactions over $10,000 in a single day with one customer.",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="Funds-transfer recordkeeping",
            form_name="Travel Rule / Recordkeeping Rule (31 CFR 1010.410)",
            authority="FinCEN",
            frequency="Continuous",
            due_date_rule="On every transmittal of funds ≥ $3,000 — name/address/account of sender and recipient retained for 5 years.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="AML Program",
            form_name="BSA / AML Program — written program, independent testing, CDD",
            authority="FinCEN",
            frequency="Continuous + Annual independent test",
            due_date_rule="Program continuously maintained; independent testing at least annually for MSBs.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="OFAC sanctions",
            form_name="OFAC sanctions screening + Annual Report of Blocked Property (TD F 90-22.50)",
            authority="OFAC",
            frequency="Continuous + Annual",
            due_date_rule="Screening on every transaction; Annual Report by 30 Sep.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="Beneficial ownership",
            form_name="FinCEN Beneficial Ownership Information (BOI) report",
            authority="FinCEN",
            frequency="Event-based",
            due_date_rule="Initial report within 90 days of formation (for entities formed in 2024); updates within 30 days of change.",
            applicability="Mandatory",
            applicability_note="Status subject to ongoing litigation — confirm latest enforcement posture before relying.",
        ),

        # === Consumer Protection (CFPB Remittance Rule) ===
        FintechFiling(
            s_no=0,
            category="Consumer Protection",
            area="Remittance Transfer Rule",
            form_name="Regulation E Subpart B (CFPB Remittance Rule) — pre-payment & receipt disclosures, error resolution, cancellation",
            authority="CFPB",
            frequency="Continuous",
            due_date_rule="Pre-payment disclosure before payment; receipt at/after payment; 30-min cancellation window; error resolution within 90 days.",
            applicability="Mandatory",
            applicability_note="Directly applicable — this is the core remittance consumer rule.",
        ),
        FintechFiling(
            s_no=0,
            category="Consumer Protection",
            area="Complaint handling",
            form_name="CFPB Consumer Complaint response",
            authority="CFPB",
            frequency="Event-based",
            due_date_rule="Initial response within 15 days; final response within 60 days of receipt.",
            applicability="Mandatory",
        ),

        # === Data Protection & Privacy ===
        FintechFiling(
            s_no=0,
            category="Data Protection & Privacy",
            area="GLBA",
            form_name="Gramm-Leach-Bliley Act — Safeguards Rule + annual privacy notice",
            authority="FTC / functional regulator",
            frequency="Continuous + Annual",
            due_date_rule="Annual privacy notice to customers; written information security program continuously maintained.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Data Protection & Privacy",
            area="State privacy laws",
            form_name="CCPA/CPRA + other state privacy law disclosures, opt-out, DSAR",
            authority="California Privacy Protection Agency + other state AGs",
            frequency="Continuous",
            due_date_rule="Privacy policy updated annually; DSAR within 45 days (extendable +45).",
            applicability="Conditional",
            applicability_note="Applies state-by-state based on consumer thresholds (CA, VA, CO, CT, UT and additional states adopting laws).",
        ),

        # === Cybersecurity ===
        FintechFiling(
            s_no=0,
            category="Cybersecurity",
            area="Payment card data",
            form_name="PCI DSS v4.0 — annual Report on Compliance / Self-Assessment Questionnaire",
            authority="Card brands / acquirers",
            frequency="Annual + Quarterly scans",
            due_date_rule="ROC/SAQ annually; ASV scans quarterly.",
            applicability="Conditional",
            applicability_note="Applies if the entity stores, processes or transmits cardholder data.",
        ),
        FintechFiling(
            s_no=0,
            category="Cybersecurity",
            area="NYDFS cybersecurity",
            form_name="NYDFS 23 NYCRR 500 — annual certification, incident notification, CISO report",
            authority="New York DFS",
            frequency="Annual + Event-based",
            due_date_rule="Annual certification by 15 Apr; incident notification within 72 hours; ransomware payment within 24 hours.",
            applicability="Conditional",
            applicability_note="Applies if licensed by NYDFS (most national money-transmitters are).",
        ),

        # === Tax ===
        FintechFiling(
            s_no=0,
            category="Direct Tax",
            area="Federal corporate tax",
            form_name="IRS Form 1120 (federal corporate income tax return) + Form 1120-W (estimated tax)",
            authority="IRS",
            frequency="Annual + Quarterly estimated",
            due_date_rule="Form 1120 by the 15th day of the 4th month after FY close (15 Apr for CY); estimated tax 15 Apr / 15 Jun / 15 Sep / 15 Dec.",
            payment_due="Estimated-tax instalment dates.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Direct Tax",
            area="Information returns",
            form_name="IRS Forms 1099 series (e.g. 1099-MISC, 1099-NEC, 1099-INT)",
            authority="IRS",
            frequency="Annual",
            due_date_rule="1099-NEC by 31 Jan; other 1099s by 28 Feb (paper) / 31 Mar (electronic).",
            applicability="Conditional",
        ),
        FintechFiling(
            s_no=0,
            category="Direct Tax",
            area="Foreign accounts",
            form_name="FBAR — FinCEN Form 114 (Report of Foreign Bank and Financial Accounts)",
            authority="FinCEN",
            frequency="Annual",
            due_date_rule="By 15 Apr for the previous calendar year (automatic extension to 15 Oct).",
            applicability="Conditional",
            applicability_note="Required if aggregate foreign account value exceeded $10,000 at any time during the year.",
        ),
        FintechFiling(
            s_no=0,
            category="Direct Tax",
            area="FATCA",
            form_name="FATCA reporting (Form 8966 / W-8/W-9 collection)",
            authority="IRS",
            frequency="Annual",
            due_date_rule="Form 8966 by 31 Mar following the reporting year.",
            applicability="Conditional",
        ),

        # === Payroll ===
        FintechFiling(
            s_no=0,
            category="Labor & Payroll",
            area="Federal payroll taxes",
            form_name="IRS Form 941 (quarterly) + Form 940 (annual FUTA) + W-2 / W-3",
            authority="IRS",
            frequency="Quarterly + Annual",
            due_date_rule="941 by end of month following quarter; 940 by 31 Jan; W-2 to employees and SSA by 31 Jan.",
            payment_due="Per IRS deposit schedule (semi-weekly or monthly depositor).",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Labor & Payroll",
            area="State payroll",
            form_name="State withholding + unemployment + SDI returns",
            authority="State revenue / labor departments",
            frequency="Quarterly / Monthly",
            due_date_rule="State-specific deposit and return cycles.",
            applicability="Mandatory",
        ),

        # === Corporate ===
        FintechFiling(
            s_no=0,
            category="Corporate & Statutory",
            area="State annual reports",
            form_name="State of incorporation annual report + franchise tax (e.g. Delaware Annual Report)",
            authority="State of incorporation",
            frequency="Annual",
            due_date_rule="Delaware: 1 Mar; other states vary — usually anniversary of incorporation.",
            payment_due="Delaware franchise tax min $400 (Authorized Shares method) or min $400 (Assumed Par Value Capital method); $50 annual report fee. Late = $200 penalty + 1.5%/month interest.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Corporate & Statutory",
            area="Foreign qualification",
            form_name="Foreign-qualification annual filings in each state of operation",
            authority="State Secretary of State offices",
            frequency="Annual",
            due_date_rule="Per state schedule.",
            applicability="Conditional",
        ),
    ]


FILINGS = _build()
