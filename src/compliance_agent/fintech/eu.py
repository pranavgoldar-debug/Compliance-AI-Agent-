"""EU (member-state-neutral) filing catalog for a remittance fintech.

Where a duty rests with the home Member State competent authority (NCA),
the entry names the function generically (e.g. 'NCA prudential return').
Substitute BaFin / CSSF / DNB / ACPR / Bank of Lithuania etc. for the
relevant Member State.
"""
from __future__ import annotations

from compliance_agent.fintech import FintechFiling


def _build() -> list[FintechFiling]:
    return [
        # === Licensing & Authorization ===
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Payment institution",
            form_name="PSD2 Payment Institution / E-Money Institution authorization & passporting notifications",
            authority="Home Member State NCA (e.g. BaFin, CSSF, ACPR, DNB, Bank of Lithuania)",
            frequency="One-time + Event-based",
            due_date_rule="Authorization before commencement; passporting notification before providing services in another Member State.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Safeguarding",
            form_name="Annual safeguarding auditor's report (client funds)",
            authority="Home Member State NCA",
            frequency="Annual",
            due_date_rule="As prescribed by NCA — typically within 4–6 months of FY close.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Prudential reporting",
            form_name="EBA REP — own funds and capital requirements return",
            authority="EBA via NCA",
            frequency="Quarterly",
            due_date_rule="Per EBA reporting calendar (typically 6 weeks after quarter close).",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Licensing & Authorization",
            area="Operational & security",
            form_name="EBA Guidelines on ICT and security risk management — annual self-assessment",
            authority="Home Member State NCA",
            frequency="Annual",
            due_date_rule="Typically aligned with FY-end reporting cycle.",
            applicability="Mandatory",
        ),

        # === AML / CFT ===
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="Suspicious transaction reporting",
            form_name="Suspicious Transaction / Activity Report to national FIU",
            authority="National FIU (e.g. FIU.NL, TRACFIN, FIU-Lux, AUSTRAC for Australia)",
            frequency="Event-based",
            due_date_rule="Without delay on forming suspicion of money laundering / terrorist financing (AMLD).",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="Funds transfer information",
            form_name="EU Regulation 2015/847 / 2023/1113 (Travel Rule) compliance — full payer/payee data on transfers",
            authority="Competent authority",
            frequency="Continuous",
            due_date_rule="On every cross-border transfer; for crypto-asset transfers per MiCA + Travel Rule from 30 Dec 2024.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="MLRO accountability",
            form_name="Annual MLRO report to senior management / Board",
            authority="Internal + on demand to NCA / FIU",
            frequency="Annual",
            due_date_rule="Per internal policy — typically within 90 days of FY close.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="AML / CFT",
            area="Business-wide risk assessment",
            form_name="Documented enterprise-wide ML/TF risk assessment refresh",
            authority="Home Member State NCA",
            frequency="Annual",
            due_date_rule="At least annually and on material change.",
            applicability="Mandatory",
        ),

        # === Consumer / Conduct ===
        FintechFiling(
            s_no=0,
            category="Consumer Protection",
            area="Cross-border payments transparency",
            form_name="Regulation (EU) 2021/1230 — disclosure of currency-conversion charges",
            authority="Home Member State NCA",
            frequency="Continuous",
            due_date_rule="Pre-transaction disclosure on every cross-border card / credit transfer with currency conversion.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Consumer Protection",
            area="Complaint handling",
            form_name="Annual complaints report to NCA / ADR body",
            authority="Home Member State NCA + ADR body",
            frequency="Annual",
            due_date_rule="Per NCA prescription — typically within 3 months of FY close.",
            applicability="Mandatory",
        ),

        # === Data Protection ===
        FintechFiling(
            s_no=0,
            category="Data Protection & Privacy",
            area="GDPR",
            form_name="GDPR — ROPA (Art. 30), DPIAs, DPO appointment, breach notification within 72h",
            authority="Lead supervisory authority (e.g. Irish DPC, CNIL)",
            frequency="Continuous + Event-based",
            due_date_rule="ROPA continuous; DPIA before high-risk processing; breach notification within 72 hours of awareness.",
            applicability="Mandatory",
        ),

        # === Cybersecurity ===
        FintechFiling(
            s_no=0,
            category="Cybersecurity",
            area="DORA (Digital Operational Resilience Act)",
            form_name="DORA — ICT risk management, third-party register, TLPT, major incident reporting",
            authority="Home Member State NCA + ESAs (EBA / ESMA / EIOPA)",
            frequency="Continuous + Event-based",
            due_date_rule="Effective 17 Jan 2025; major ICT incident initial notification within 4 hours of classification (max 24h from detection).",
            applicability="Mandatory",
            applicability_note="DORA explicitly covers payment institutions and EMIs.",
        ),
        FintechFiling(
            s_no=0,
            category="Cybersecurity",
            area="NIS2",
            form_name="NIS2 — registration with competent authority, early warning 24h, notification 72h, final report 1m",
            authority="National NIS2 competent authority",
            frequency="Event-based",
            due_date_rule="As per Article 23 timelines (24h / 72h / 1 month).",
            applicability="Conditional",
            applicability_note="Applies if classified as essential / important under national NIS2 transposition.",
        ),

        # === Tax (member-state-specific, names generic) ===
        FintechFiling(
            s_no=0,
            category="Indirect Tax (VAT)",
            area="VAT returns",
            form_name="VAT returns (monthly or quarterly, per State)",
            authority="National tax authority",
            frequency="Monthly / Quarterly",
            due_date_rule="Member-state-specific — typically by 10th–25th of following month/quarter.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Indirect Tax (VAT)",
            area="Recapitulative statement",
            form_name="EC Sales List / Intrastat (where applicable)",
            authority="National tax authority",
            frequency="Monthly / Quarterly",
            due_date_rule="Member-state-specific; Intrastat thresholds apply.",
            applicability="Conditional",
        ),
        FintechFiling(
            s_no=0,
            category="Indirect Tax (VAT)",
            area="DAC7",
            form_name="DAC7 — digital platform operator reporting",
            authority="National tax authority",
            frequency="Annual",
            due_date_rule="By 31 Jan for the previous calendar year.",
            applicability="Conditional",
            applicability_note="Triggered if the platform facilitates reportable activities (mostly relevant for marketplace components).",
        ),
        FintechFiling(
            s_no=0,
            category="Direct Tax",
            area="Corporate income tax",
            form_name="Annual corporate income tax return + advance payments",
            authority="National tax authority",
            frequency="Annual + Periodic instalments",
            due_date_rule="Member-state-specific; e.g. NL 5 months after FY close, IE within 9 months, DE 31 Jul (extendable).",
            payment_due="Per advance-payment cycle.",
            applicability="Mandatory",
        ),

        # === Corporate ===
        FintechFiling(
            s_no=0,
            category="Corporate & Statutory",
            area="Companies registry",
            form_name="Annual accounts + management report filing with national companies registry",
            authority="National companies registry (e.g. KVK, RCS Lux, Handelsregister)",
            frequency="Annual",
            due_date_rule="Member-state-specific — typically 6–8 months after FY close.",
            applicability="Mandatory",
        ),
        FintechFiling(
            s_no=0,
            category="Corporate & Statutory",
            area="Beneficial ownership",
            form_name="UBO register updates",
            authority="National UBO register",
            frequency="Event-based + Annual confirm",
            due_date_rule="Updates within prescribed days of change; annual confirmation as required.",
            applicability="Mandatory",
        ),
    ]


FILINGS = _build()
