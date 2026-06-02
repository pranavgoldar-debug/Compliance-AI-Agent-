"""Filings extracted from the Aspora Global Compliance Tracker spreadsheet.

These are the real country-wide compliance filings (tax, corporate,
regulatory) the group tracks per jurisdiction. They're merged into the
fintech CATALOG so that — once an entity holds a licence in a country —
the whole country's filing set shows up as applicable and can be put on
the calendar. Data is extracted from the sheet, not the file itself.

Each entry: (category, area, form_name, authority, frequency,
due_date_rule, payment_due). Applicability defaults to Mandatory.
"""
from __future__ import annotations

from compliance_agent.fintech import FintechFiling


def _f(category, area, form_name, authority, frequency, due, pay=None):
    return FintechFiling(
        s_no=0,
        category=category,
        area=area,
        form_name=form_name,
        authority=authority,
        frequency=frequency,
        due_date_rule=due,
        payment_due=pay,
        applicability="Mandatory",
    )


# ---------------------------------------------------------------------------
# United Kingdom
# ---------------------------------------------------------------------------
_UK = [
    _f("Pensions", "Auto-enrolment pension contributions", "Pension remittance", "The Pensions Regulator / Pension provider", "Monthly", "Typically by 22nd of the month following deduction (scheme rules apply).", "Same as scheme rules"),
    _f("Tax", "Indirect Tax", "VAT return (MTD)", "HMRC", "Quarterly", "One month and 7 days after the VAT period end.", "Same as filing deadline"),
    _f("Tax", "Employment Tax", "PAYE / RTI (FPS/EPS)", "HMRC", "Monthly", "On or before each payroll date; payment by 22nd of the following month.", "By 22nd of following month"),
    _f("Tax", "CIS", "Construction Industry Scheme (CIS300)", "HMRC", "Monthly", "Return by 19th; payment by 22nd (electronic) following the tax month.", "22nd (electronic)"),
    _f("Corporate Tax", "Direct Tax", "Corporation Tax return (CT600)", "HMRC", "Annual", "12 months after the accounting period end.", None),
    _f("Corporate Tax", "Direct Tax", "Corporation Tax payment", "HMRC", "Annual", "9 months and 1 day after the accounting period end.", "Tax payable 9 months + 1 day from period end"),
    _f("Corporate Law", "Statutory Filings", "Statutory accounts filing (Companies House)", "Companies House", "Annual", "Private company: within 9 months after the financial year end.", None),
    _f("Corporate Law", "Statutory Filings", "Confirmation Statement (CS01)", "Companies House", "Annual", "Within 14 days of the made-up date (every 12 months).", "Filing fee"),
    _f("Corporate Records", "Governance", "PSC Register Update", "Companies House", "Event-based", "Within 14 days of the change.", None),
    _f("Financial Regulation", "Regulatory Reporting", "FCA Periodic Regulatory Return (RegData)", "FCA", "Semi-Annual / Annual", "Within 2 months after the reporting period end.", None),
    _f("Financial Regulation", "Regulatory Reporting", "FCA quarterly data return (FIN073)", "FCA", "Quarterly", "25th of the month following the quarter.", None),
    _f("Financial Regulation", "Risk & Fraud", "Fraud Reporting (REP017)", "FCA", "Periodic", "As per the FCA reporting schedule.", None),
    _f("Financial Regulation", "Consumer Protection", "Complaints Reporting (DISP)", "FCA", "Annual / Semi-Annual", "As per FCA DISP rules.", None),
    _f("Financial Regulation", "Governance", "Change Notifications (Controllers, Directors, Business Model)", "FCA", "Event-based", "Immediately / prior approval where required.", None),
    _f("AML / CTF", "Compliance", "AML Risk Assessment & Policy Review", "FCA / HMRC", "Annual", "Annually (best practice).", None),
    _f("Data Protection", "Compliance", "ICO Registration Renewal", "ICO", "Annual", "By the anniversary of the ICO registration.", "Annual ICO fee"),
    _f("Regulatory", "Business/Activity Licenses", "Business / Activity Licence renewal", "Relevant regulator / Local authority", "Annual / As per licence", "Per licence conditions.", "Renewal fee"),
]

# ---------------------------------------------------------------------------
# United Arab Emirates
# ---------------------------------------------------------------------------
_UAE = [
    _f("Social Security", "Pension for UAE/GCC Nationals", "GPSSA monthly contribution", "GPSSA", "Monthly", "Pay by the following month.", "Employer (~12.5%) & employee (~5%)"),
    _f("VAT", "VAT", "VAT201", "FTA", "Monthly / Quarterly", "Within 28 days after the period end.", "Same as filing deadline"),
    _f("Corporate Tax", "Registration", "Corporate Income Tax registration", "FTA", "One-time", "Within 3 months of incorporation / crossing threshold.", None),
    _f("Corporate Tax", "Direct Tax", "Corporate Income Tax return", "FTA", "Annual", "Within 9 months after the financial year end.", "Same date"),
    _f("Excise Tax", "Excise", "Excise tax return", "FTA", "Monthly", "Within 15 days after the period end.", "Same as filing deadline"),
    _f("Regulatory", "Economic Substance", "Economic Substance – Notification (ESR)", "UAE MOF", "Annual (if in scope)", "Within 6 months after the end of the reportable year.", None),
    _f("Regulatory", "Economic Substance", "Economic Substance – Report (ESR)", "UAE MOF", "Annual (if in scope)", "Within 12 months after the end of the reportable year.", None),
    _f("Regulatory", "Ultimate Beneficial Owner", "Ultimate Beneficial Owner (UBO) filing", "MOE / Free Zone Authority", "On change & annual confirmation", "Within 15 days of a change.", None),
    _f("Regulatory", "Trade Licensing", "Trade / Commercial License Renewal", "DED / Free Zone Authority", "Annual", "By the anniversary of licence issuance (grace varies by zone).", "Renewal fee"),
]

# ---------------------------------------------------------------------------
# Canada
# ---------------------------------------------------------------------------
_CANADA = [
    _f("Provincial Payroll Taxes", "Employer Health Tax / Payroll levies", "Provincial payroll tax return", "Provincial Ministries of Finance", "Monthly / Quarterly / Annual", "Commonly by the 15th after period; annual returns often mid-March (province-specific).", "Same as due date"),
    _f("Workers' Compensation", "Workers' compensation premiums", "WSIB / WCB returns", "Provincial WCB / WSIB", "Monthly / Quarterly / Annual", "Per assessment schedule.", "Per schedule"),
    _f("GST/HST", "GST/HST", "GST/HST return (GST34 / RC159)", "CRA", "Monthly / Quarterly / Annual", "Monthly/Quarterly: 1 month after period end; Annual (most corps): 3 months after YE.", "Same as filing deadline"),
    _f("PST/QST", "Provincial sales tax", "Provincial sales tax return", "Provincial tax authorities / Revenu Québec", "Monthly / Quarterly / Annual", "Varies by province (commonly month-end following period).", "Same as filing deadline"),
    _f("Corporate Tax", "Direct Tax", "Corporate income tax return (T2)", "CRA (and Revenu Québec for QC)", "Annual", "6 months after the fiscal year end.", None),
    _f("Corporate Tax", "Direct Tax", "Corporate income tax payment (T2 / instalments)", "CRA (and Revenu Québec for QC)", "Monthly / Quarterly instalments; annual balance", "Balance due 2 months after YE (3 months for many CCPCs).", "As per schedule"),
    _f("Information Returns", "Investment income", "T5 / T5 Summary", "CRA", "Annual", "Last day of February following the calendar year.", None),
    _f("Information Returns", "Contract Payment Reporting", "T5018", "CRA", "Annual or monthly/quarterly (elective)", "6 months after the reporting period end.", None),
    _f("Information Returns", "Non-resident payments", "NR4", "CRA", "Annual", "Last day of March following the calendar year.", "Withholding remitted by 15th of following month"),
    _f("Regulatory", "Registry", "Corporate annual return (registry)", "Corporations Canada / Provincial registries", "Annual", "By the anniversary date (jurisdiction-specific grace periods).", "Filing fee"),
]

# ---------------------------------------------------------------------------
# United States
# ---------------------------------------------------------------------------
_US = [
    _f("Information Returns", "W-2 wage reporting", "Forms W-2 / W-3", "SSA / IRS", "Annual", "Due Jan 31 to employees and the SSA.", None),
    _f("Information Returns", "Non-employee comp", "Form 1099-NEC", "IRS", "Annual", "Recipient & IRS: Jan 31 (e-file required if >=10 total info returns).", None),
    _f("Information Returns", "Rents, prizes, etc.", "Form 1099-MISC", "IRS", "Annual", "Recipients: Jan 31; IRS: Feb 28 (paper) / Mar 31 (e-file).", None),
    _f("Information Returns", "ACA for ALEs", "Forms 1095-C / 1094-C", "IRS", "Annual", "Furnish by Mar 2; IRS: Feb 28 (paper) / Mar 31 (e-file).", None),
    _f("Information Returns", "Nonresident withholding", "Forms 1042-S / 1042", "IRS", "Annual + periodic deposits", "1042-S & 1042: Mar 15; deposits via EFTPS per s.6302 rules.", "With deposits/return"),
    _f("Sales/Use Tax", "State & local sales/use tax", "State / Local sales tax returns", "State & local tax depts.", "Monthly / Quarterly / Annual", "Often by 20th or end of month following period (varies by state).", "Same as filing deadlines"),
    _f("Corporate Tax", "Direct Tax", "C-Corp income tax return (Form 1120 + 7004)", "IRS", "Annual + quarterly estimates", "Return: 15th day of 4th month after YE; estimates: 4th/6th/9th/12th months.", "With estimates/return"),
    _f("Regulatory", "State filings", "State annual report / franchise tax", "State SOS / Revenue", "Annual / Biennial", "Varies by state (e.g. DE franchise tax by Mar 1; LLC annual tax by Jun 1).", "Per state schedule"),
    _f("Regulatory", "Beneficial Ownership", "FinCEN BOI (BOIR)", "FinCEN (US Treasury)", "One-time + updates", "Per FinCEN timelines; updates within 30 days of change.", None),
    _f("Unclaimed Property", "Escheatment", "State unclaimed property reports", "State treasurers / unclaimed property divisions", "Annual", "Commonly Oct–Nov (Jul for some, Mar for others e.g. DE).", "With report"),
]

# ---------------------------------------------------------------------------
# Lithuania
# ---------------------------------------------------------------------------
_LITHUANIA = [
    _f("Social Security", "Social Security (VSD/PSD)", "SAM", "Sodra", "Monthly", "15th of the following month.", "By the same date (15th)"),
    _f("VAT", "VAT", "VAT return (FR0600 / PVM deklaracija)", "VMI", "Monthly (quarterly/bi-annual for small taxpayers)", "25th of the following month.", "Same as filing deadline"),
    _f("VAT", "VAT ledgers", "i.SAF", "VMI (i.MAS)", "Monthly", "20th of the following month.", None),
    _f("EU Reporting", "EC Sales List", "FR0564", "VMI", "Monthly (or quarterly)", "25th of the following month.", None),
    _f("Statistics", "Intrastat", "Intrastat", "Statistics Lithuania (LSD)", "Monthly (if applicable)", "10th working day of the following month.", None),
    _f("VAT", "e-Waybills", "i.VAZ", "VMI (i.MAS)", "Per consignment", "Before/at start of transport; updates on changes.", None),
    _f("Corporate Tax", "Direct Tax", "Corporate income tax return (PLN204)", "VMI", "Annual", "15th day of the 6th month after YE (e.g. 15 Jun for 31 Dec YE).", "By the return due date"),
    _f("Corporate Tax", "Direct Tax", "Advance CIT", "VMI", "Quarterly", "15th day of the last month of each quarter.", "Same date"),
    _f("Regulatory", "Annual financial statements", "Annual FS package", "Register of Legal Entities (Registrų centras / JAR)", "Annual", "Approve within 4 months after YE; file within 30 days of approval (~31 May for 31 Dec YE).", None),
    _f("Regulatory", "Statutory audit", "Audited FS (if in scope)", "Lithuanian Chamber of Auditors / Registrų centras", "Annual (if thresholds met)", "Complete before the FS filing deadline.", None),
    _f("Regulatory", "Beneficial Ownership", "Beneficial Ownership (JANGIS)", "Registrų centras", "On change", "Within 10 calendar days of a change.", None),
    _f("Accounting Control", "Year-end inventory", "Year-end inventory count", "Internal control", "Annual", "Before FS preparation; by fiscal year end.", None),
]


# country_code -> filings extracted from the spreadsheet
TRACKER: dict[str, list[FintechFiling]] = {
    "uk": _UK,
    "uae": _UAE,
    "canada": _CANADA,
    "us": _US,
    "lithuania": _LITHUANIA,
}
