"""Curated regulator source URLs for the most common filings.

Each entry is a list of `(needles, url)` pairs scoped to one jurisdiction.
We match by checking whether ALL needle tokens appear in the rule's
form_name (case-insensitive). First match wins. This deliberately favours
authority-level landing pages (e.g. HMRC's VAT guide, MCA's home) over
hyper-specific form URLs — the goal is "click to start", not "directly
download the PDF".

The patterns are ordered most-specific-first within each jurisdiction so
broad fallbacks (e.g. "rbi" → rbi.org.in homepage) only fire for forms
the more targeted patterns missed.

Update this file when:
  - A regulator moves a page (URLs rot; that's normal)
  - A new rule lands in the catalog that you want auto-linked

To apply changes to an already-seeded DB:
    python -m compliance_agent.cli backfill-source-urls
"""
from __future__ import annotations

from typing import Optional


# Each entry: (list-of-tokens-that-must-all-appear-in-form-name, url)
# Order matters within a jurisdiction; first match wins.
_HINTS: dict[str, list[tuple[list[str], str]]] = {
    # -------------------------------------------------------------------
    # India — RBI, MCA, GST, Income Tax, FIU-IND, EPFO, ESIC, MEITY
    # -------------------------------------------------------------------
    "india": [
        # --- AML / FIU-IND ---
        ("ctr cash transaction".split(), "https://fiuindia.gov.in/files/AML_Legislation/PML_rules.html"),
        ("cash transaction report".split(), "https://fiuindia.gov.in/files/AML_Legislation/PML_rules.html"),
        ("str suspicious".split(), "https://fiuindia.gov.in/files/AML_Legislation/PML_rules.html"),
        ("cross-border wire".split(), "https://fiuindia.gov.in/files/AML_Legislation/PML_rules.html"),
        ("cbwtr".split(), "https://fiuindia.gov.in/files/AML_Legislation/PML_rules.html"),
        ("counterfeit currency".split(), "https://fiuindia.gov.in/"),
        ("ccr".split(), "https://fiuindia.gov.in/"),
        ("non-profit organization".split(), "https://fiuindia.gov.in/"),
        ("ntr".split(), "https://fiuindia.gov.in/"),
        ("pmla compliance".split(), "https://fiuindia.gov.in/"),
        ("re-kyc".split(), "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/MDKYC2016_25052021.pdf"),
        ("hvtr".split(), "https://fiuindia.gov.in/"),
        ("high-value transaction".split(), "https://fiuindia.gov.in/"),

        # --- Payments / RBI authorizations ---
        ("pa-pg".split(), "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=49926"),
        ("pa-cb".split(), "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12549"),
        ("mtss".split(), "https://www.rbi.org.in/Scripts/FAQView.aspx?Id=66"),
        ("rda authorized dealer".split(), "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11993"),
        ("half-yearly rda".split(), "https://www.rbi.org.in/Scripts/FAQView.aspx?Id=66"),
        ("rbi system audit".split(), "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12159"),
        ("rbi cyber fraud".split(), "https://www.rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx?Id=12131"),
        ("rbi ombudsman".split(), "https://www.rbi.org.in/scripts/Complaints.aspx"),
        ("customer grievance".split(), "https://www.rbi.org.in/scripts/Complaints.aspx"),
        ("fair-practice".split(), "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11983"),

        # --- Forex / FEMA / RBI returns ---
        ("fla annual".split(), "https://flair.rbi.org.in/"),
        ("fc-gpr".split(), "https://firms.rbi.org.in/"),
        ("fc-trs".split(), "https://firms.rbi.org.in/"),
        ("ecb-2".split(), "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12380"),
        ("ecb".split(), "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12380"),
        ("apr overseas".split(), "https://firms.rbi.org.in/"),
        ("apr".split(), "https://firms.rbi.org.in/"),
        ("odi".split(), "https://firms.rbi.org.in/"),

        # --- Income tax / TDS / TCS ---
        ("15ca".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1"),
        ("15cb".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1"),
        ("advance tax".split(), "https://www.incometax.gov.in/iec/foportal/help/all-topics/payment-of-taxes"),
        ("itns 280".split(), "https://www.incometax.gov.in/iec/foportal/help/all-topics/payment-of-taxes"),
        ("itns 281".split(), "https://www.incometax.gov.in/iec/foportal/help/all-topics/payment-of-taxes"),
        ("tds deposit".split(), "https://www.incometax.gov.in/iec/foportal/help/all-topics/payment-of-taxes"),
        ("24q".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-tds"),
        ("26q".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-tds"),
        ("27q".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-tds"),
        ("27eq".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-tds"),
        ("tcs lrs".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-tds"),
        ("form 16".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1"),
        ("itr-6".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1"),
        ("3ca-3cd".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1"),
        ("tax audit".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1"),
        ("3ceb".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1"),
        ("3cead".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1"),
        ("country-by-country".split(), "https://www.incometax.gov.in/iec/foportal/help/all-topics/itr-filing/cbc"),
        ("61a".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1"),
        ("sft".split(), "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1"),

        # --- GST ---
        ("gstr-1".split(), "https://www.gst.gov.in/help/returns"),
        ("gstr-3b".split(), "https://www.gst.gov.in/help/returns"),
        ("gstr-7".split(), "https://www.gst.gov.in/help/returns"),
        ("gstr-9c".split(), "https://www.gst.gov.in/help/returns/annualreturns"),
        ("gstr-9".split(), "https://www.gst.gov.in/help/returns/annualreturns"),
        ("gstr-2b".split(), "https://www.gst.gov.in/help/returns"),
        ("gst e-invoicing".split(), "https://einvoice1.gst.gov.in/"),
        ("gst".split(), "https://www.gst.gov.in/help/returns"),

        # --- MCA / Companies Act ---
        ("aoc-4".split(), "https://www.mca.gov.in/MinistryV2/companyformsdownload.html"),
        ("mgt-7".split(), "https://www.mca.gov.in/MinistryV2/companyformsdownload.html"),
        ("adt-1".split(), "https://www.mca.gov.in/MinistryV2/companyformsdownload.html"),
        ("dir-3 kyc".split(), "https://www.mca.gov.in/MinistryV2/companyformsdownload.html"),
        ("dpt-3".split(), "https://www.mca.gov.in/MinistryV2/companyformsdownload.html"),
        ("msme-1".split(), "https://www.mca.gov.in/MinistryV2/companyformsdownload.html"),
        ("ben-2".split(), "https://www.mca.gov.in/MinistryV2/companyformsdownload.html"),
        ("inc-20a".split(), "https://www.mca.gov.in/MinistryV2/companyformsdownload.html"),
        ("csr-2".split(), "https://www.mca.gov.in/MinistryV2/companyformsdownload.html"),
        ("chg-1".split(), "https://www.mca.gov.in/MinistryV2/companyformsdownload.html"),
        ("chg-4".split(), "https://www.mca.gov.in/MinistryV2/companyformsdownload.html"),
        ("board meetings".split(), "https://www.mca.gov.in/content/mca/global/en/acts-rules/ebooks/companies-act.html"),

        # --- Labour ---
        ("epf".split(), "https://www.epfindia.gov.in/site_en/index.php"),
        ("esi".split(), "https://www.esic.in/web/esic/home"),
        ("professional tax".split(), "https://www.shramsuvidha.gov.in/"),
        ("pt returns".split(), "https://www.shramsuvidha.gov.in/"),
        ("lwf".split(), "https://www.shramsuvidha.gov.in/"),
        ("gratuity".split(), "https://www.shramsuvidha.gov.in/"),
        ("posh".split(), "https://wcd.nic.in/sites/default/files/Handbook%20on%20Sexual%20Harassment%20of%20Women%20at%20Workplace.pdf"),
        ("shops establishments".split(), "https://www.shramsuvidha.gov.in/"),

        # --- Data / cyber ---
        ("dpdp".split(), "https://www.meity.gov.in/data-protection-framework"),
        ("digital personal data".split(), "https://www.meity.gov.in/data-protection-framework"),
        ("cert-in".split(), "https://www.cert-in.org.in/"),
        ("ict log".split(), "https://www.cert-in.org.in/"),

        # --- IFSCA / GIFT ---
        ("ifsca".split(), "https://ifsca.gov.in/"),

        # --- DGFT ---
        ("iec".split(), "https://www.dgft.gov.in/CP/?opt=iec"),
        ("importer-exporter".split(), "https://www.dgft.gov.in/CP/?opt=iec"),

        # --- Fallbacks ---
        (["rbi"], "https://www.rbi.org.in/"),
        (["mca"], "https://www.mca.gov.in/"),
        (["pmla"], "https://fiuindia.gov.in/"),
    ],

    # -------------------------------------------------------------------
    # United States — FinCEN, IRS, OFAC, NMLS, CFPB, NYDFS, state
    # -------------------------------------------------------------------
    "us": [
        # --- FinCEN ---
        ("fincen 107".split(), "https://www.fincen.gov/msb-registration"),
        ("msb registration".split(), "https://www.fincen.gov/msb-registration"),
        ("nmls".split(), "https://www.csbs.org/nationwide-multistate-licensing-system-nmls"),
        ("money transmitter".split(), "https://www.csbs.org/nationwide-multistate-licensing-system-nmls"),
        ("surety bond".split(), "https://www.csbs.org/nationwide-multistate-licensing-system-nmls"),
        ("fincen sar".split(), "https://www.fincen.gov/resources/filing-information"),
        ("fincen 111".split(), "https://www.fincen.gov/resources/filing-information"),
        ("fincen ctr".split(), "https://www.fincen.gov/resources/filing-information"),
        ("fincen 112".split(), "https://www.fincen.gov/resources/filing-information"),
        ("travel rule".split(), "https://www.fincen.gov/resources/statutes-regulations/funds-travel-regulations"),
        ("31 cfr 1010.410".split(), "https://www.fincen.gov/resources/statutes-regulations/funds-travel-regulations"),
        ("bsa aml".split(), "https://www.fincen.gov/resources/statutes-and-regulations/bank-secrecy-act"),
        ("beneficial ownership".split(), "https://www.fincen.gov/boi"),
        ("boi".split(), "https://www.fincen.gov/boi"),
        ("form 8300".split(), "https://www.irs.gov/businesses/small-businesses-self-employed/form-8300-and-reporting-cash-payments-of-over-10000"),
        ("fbar".split(), "https://www.fincen.gov/report-foreign-bank-and-financial-accounts"),
        ("form 114".split(), "https://www.fincen.gov/report-foreign-bank-and-financial-accounts"),

        # --- OFAC ---
        ("ofac".split(), "https://ofac.treasury.gov/"),
        ("blocked property".split(), "https://ofac.treasury.gov/recent-actions"),
        ("td f 90-22.50".split(), "https://ofac.treasury.gov/recent-actions"),

        # --- IRS ---
        ("form 1120-w".split(), "https://www.irs.gov/forms-pubs/about-form-1120-w"),
        ("form 1120".split(), "https://www.irs.gov/forms-pubs/about-form-1120"),
        ("form 1099".split(), "https://www.irs.gov/forms-pubs/about-form-1099-misc"),
        ("form 941".split(), "https://www.irs.gov/forms-pubs/about-form-941"),
        ("form 940".split(), "https://www.irs.gov/forms-pubs/about-form-940"),
        ("w-2".split(), "https://www.irs.gov/forms-pubs/about-form-w-2"),
        ("w-3".split(), "https://www.irs.gov/forms-pubs/about-form-w-3"),
        ("form 8966".split(), "https://www.irs.gov/businesses/corporations/fatca-foreign-financial-institution-list-search-and-download-tool"),
        ("fatca".split(), "https://www.irs.gov/businesses/corporations/foreign-account-tax-compliance-act-fatca"),
        ("form 1042".split(), "https://www.irs.gov/forms-pubs/about-form-1042"),
        ("form 8938".split(), "https://www.irs.gov/forms-pubs/about-form-form-8938"),
        ("form 5471".split(), "https://www.irs.gov/forms-pubs/about-form-5471"),
        ("tic".split(), "https://home.treasury.gov/data/treasury-international-capital-tic-system"),
        ("treasury international capital".split(), "https://home.treasury.gov/data/treasury-international-capital-tic-system"),

        # --- CFPB ---
        ("regulation e".split(), "https://www.consumerfinance.gov/rules-policy/regulations/1005/"),
        ("cfpb remittance".split(), "https://www.consumerfinance.gov/rules-policy/regulations/1005/"),
        ("cfpb consumer complaint".split(), "https://www.consumerfinance.gov/complaint/"),
        ("regulation b".split(), "https://www.consumerfinance.gov/rules-policy/regulations/1002/"),
        ("ecoa".split(), "https://www.consumerfinance.gov/rules-policy/regulations/1002/"),
        ("regulation z".split(), "https://www.consumerfinance.gov/rules-policy/regulations/1026/"),
        ("tila".split(), "https://www.consumerfinance.gov/rules-policy/regulations/1026/"),
        ("udaap".split(), "https://www.consumerfinance.gov/compliance/supervisory-guidance/unfair-deceptive-abusive-acts-or-practices/"),

        # --- State + corporate ---
        ("delaware annual report".split(), "https://corp.delaware.gov/paytaxes/"),
        ("franchise tax".split(), "https://corp.delaware.gov/paytaxes/"),
        ("state sales".split(), "https://www.taxadmin.org/state-tax-agencies"),
        ("foreign-qualification".split(), "https://www.taxadmin.org/state-tax-agencies"),
        ("state withholding".split(), "https://www.taxadmin.org/state-tax-agencies"),
        ("state unclaimed property".split(), "https://www.unclaimed.org/"),

        # --- Privacy + cyber ---
        ("ccpa".split(), "https://oag.ca.gov/privacy/ccpa"),
        ("cpra".split(), "https://oag.ca.gov/privacy/ccpa"),
        ("gramm-leach-bliley".split(), "https://www.ftc.gov/business-guidance/privacy-security/gramm-leach-bliley-act"),
        ("safeguards rule".split(), "https://www.ftc.gov/business-guidance/privacy-security/gramm-leach-bliley-act"),
        ("nydfs 500".split(), "https://www.dfs.ny.gov/industry_guidance/cybersecurity"),
        ("nydfs".split(), "https://www.dfs.ny.gov/industry_guidance/cybersecurity"),
        ("pci dss".split(), "https://www.pcisecuritystandards.org/document_library/"),

        # --- Employment + safety ---
        ("tcpa".split(), "https://www.fcc.gov/general/telemarketing-and-robocalls"),
        ("can-spam".split(), "https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business"),
        ("osha".split(), "https://www.osha.gov/recordkeeping"),
        ("eeo-1".split(), "https://www.eeocdata.org/eeo1"),
        ("sarbanes-oxley".split(), "https://www.sec.gov/about/laws/soa2002.pdf"),

        # --- Fallbacks ---
        (["irs"], "https://www.irs.gov/"),
        (["fincen"], "https://www.fincen.gov/"),
    ],

    # -------------------------------------------------------------------
    # United Kingdom — FCA, HMRC, Companies House, ICO, BoE, ONS, NCA, TPR
    # -------------------------------------------------------------------
    "uk": [
        # --- FCA / payment institutions ---
        ("fca authorised payment".split(), "https://www.fca.org.uk/firms/payment-services-electronic-money"),
        ("psr 2017".split(), "https://www.fca.org.uk/firms/payment-services-electronic-money"),
        ("fca regulatory returns".split(), "https://www.fca.org.uk/firms/regulatory-reporting"),
        ("regdata".split(), "https://www.fca.org.uk/firms/regdata"),
        ("fsa056".split(), "https://www.fca.org.uk/firms/fees/calculate-your-annual-fee"),
        ("fin073".split(), "https://www.fca.org.uk/firms/financial-crime/annual-financial-crime-report"),
        ("rep-crim".split(), "https://www.fca.org.uk/firms/financial-crime/annual-financial-crime-report"),
        ("rep017".split(), "https://www.fca.org.uk/firms/regulatory-reporting"),
        ("rep018".split(), "https://www.fca.org.uk/firms/regulatory-reporting"),
        ("smcr".split(), "https://www.fca.org.uk/firms/senior-managers-certification-regime"),
        ("consumer duty".split(), "https://www.fca.org.uk/firms/consumer-duty"),
        ("disp complaints".split(), "https://www.fca.org.uk/firms/complaints"),
        ("financial ombudsman".split(), "https://www.financial-ombudsman.org.uk/businesses"),
        ("psr authorised push payment".split(), "https://www.psr.org.uk/our-work/app-scams/"),
        ("operational resilience".split(), "https://www.fca.org.uk/firms/operational-resilience"),
        ("principle 11".split(), "https://www.handbook.fca.org.uk/handbook/PRIN/2/"),
        ("financial services compensation scheme".split(), "https://www.fscs.org.uk/about-us/firm/"),
        ("fscs".split(), "https://www.fscs.org.uk/about-us/firm/"),
        ("safeguarding audit".split(), "https://www.fca.org.uk/firms/payment-services-electronic-money/safeguarding"),
        ("safeguarding reconciliation".split(), "https://www.fca.org.uk/firms/payment-services-electronic-money/safeguarding"),

        # --- AML / NCA / OFSI ---
        ("daml".split(), "https://www.nationalcrimeagency.gov.uk/what-we-do/crime-threats/money-laundering-and-illicit-finance/suspicious-activity-reports"),
        ("sar online".split(), "https://www.nationalcrimeagency.gov.uk/what-we-do/crime-threats/money-laundering-and-illicit-finance/suspicious-activity-reports"),
        ("sar nca".split(), "https://www.nationalcrimeagency.gov.uk/what-we-do/crime-threats/money-laundering-and-illicit-finance/suspicious-activity-reports"),
        ("ofsi".split(), "https://www.gov.uk/government/organisations/office-of-financial-sanctions-implementation"),
        ("mlro".split(), "https://www.fca.org.uk/firms/financial-crime"),
        ("hmrc aml".split(), "https://www.gov.uk/guidance/money-laundering-regulations-who-needs-to-register"),

        # --- HMRC / tax ---
        ("vat return".split(), "https://www.gov.uk/vat-returns"),
        ("making tax digital".split(), "https://www.gov.uk/vat-record-keeping/making-tax-digital-for-vat"),
        ("ct600".split(), "https://www.gov.uk/government/publications/corporation-tax-company-tax-return-ct600-2008-version-2"),
        ("corporation tax".split(), "https://www.gov.uk/corporation-tax"),
        ("paye".split(), "https://www.gov.uk/paye-for-employers"),
        ("rti".split(), "https://www.gov.uk/running-payroll/reporting-to-hmrc"),
        ("p11d".split(), "https://www.gov.uk/government/publications/paye-p11d-expenses-and-benefits-for-the-tax-year"),
        ("ers".split(), "https://www.gov.uk/government/collections/employment-related-securities"),
        ("emi".split(), "https://www.gov.uk/tax-employee-share-schemes/enterprise-management-incentives-emis"),
        ("sao certificate".split(), "https://www.gov.uk/guidance/the-senior-accounting-officer-regime"),
        ("senior accounting officer".split(), "https://www.gov.uk/guidance/the-senior-accounting-officer-regime"),
        ("crs".split(), "https://www.gov.uk/government/publications/automatic-exchange-of-information-introduction"),
        ("ir35".split(), "https://www.gov.uk/guidance/understanding-off-payroll-working-ir35"),
        ("off-payroll".split(), "https://www.gov.uk/guidance/understanding-off-payroll-working-ir35"),
        ("cis300".split(), "https://www.gov.uk/what-is-the-construction-industry-scheme"),
        ("intrastat".split(), "https://www.gov.uk/intrastat"),

        # --- Companies House ---
        ("confirmation statement".split(), "https://www.gov.uk/file-an-annual-return-with-companies-house"),
        ("cs01".split(), "https://www.gov.uk/file-an-annual-return-with-companies-house"),
        ("psc".split(), "https://www.gov.uk/government/publications/guidance-to-the-people-with-significant-control-requirements-for-companies-and-limited-liability-partnerships"),
        ("economic crime".split(), "https://www.gov.uk/government/collections/economic-crime-and-corporate-transparency-act-2023"),
        ("corporate transparency".split(), "https://www.gov.uk/government/collections/economic-crime-and-corporate-transparency-act-2023"),

        # --- TPR / pensions ---
        ("auto-enrolment".split(), "https://www.thepensionsregulator.gov.uk/en/employers"),
        ("re-enrolment".split(), "https://www.thepensionsregulator.gov.uk/en/employers"),
        ("declaration of compliance".split(), "https://www.thepensionsregulator.gov.uk/en/employers"),
        ("tpr".split(), "https://www.thepensionsregulator.gov.uk/"),

        # --- ICO / data ---
        ("uk gdpr".split(), "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/"),
        ("ico".split(), "https://ico.org.uk/for-organisations/"),

        # --- BoE / ONS ---
        ("bank of england".split(), "https://www.bankofengland.co.uk/statistics/data-collection"),
        ("office for national statistics".split(), "https://www.ons.gov.uk/surveys"),
        ("ons business".split(), "https://www.ons.gov.uk/surveys"),

        # --- Misc ---
        ("modern slavery".split(), "https://www.gov.uk/government/collections/modern-slavery-bill"),
        ("gender pay gap".split(), "https://gender-pay-gap.service.gov.uk/"),

        # --- Fallbacks ---
        (["fca"], "https://www.fca.org.uk/firms/regulatory-reporting"),
        (["hmrc"], "https://www.gov.uk/government/organisations/hm-revenue-customs"),
    ],

    # -------------------------------------------------------------------
    # European Union — Commission, EBA, ECB, EUR-Lex, OECD
    # -------------------------------------------------------------------
    "eu": [
        ("psd2".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32015L2366"),
        ("psd3".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A52023PC0367"),
        ("e-money institution".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32009L0110"),
        ("payment institution".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32015L2366"),
        ("passporting".split(), "https://www.eba.europa.eu/regulation-and-policy/passporting"),
        ("safeguarding".split(), "https://www.eba.europa.eu/regulation-and-policy/payment-services-and-electronic-money"),

        # AML / Travel Rule
        ("travel rule".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32023R1113"),
        ("2015/847".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32015R0847"),
        ("2023/1113".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32023R1113"),
        ("currency-conversion".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32021R1230"),
        ("2021/1230".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32021R1230"),
        ("ml/tf risk assessment".split(), "https://www.eba.europa.eu/regulation-and-policy/anti-money-laundering-and-countering-financing-terrorism"),
        ("mlro".split(), "https://www.eba.europa.eu/regulation-and-policy/anti-money-laundering-and-countering-financing-terrorism"),

        # EBA
        ("eba rep".split(), "https://www.eba.europa.eu/risk-and-data-analysis/reporting-frameworks"),
        ("eba fraud".split(), "https://www.eba.europa.eu/regulation-and-policy/payment-services-and-electronic-money"),
        ("eba guidelines".split(), "https://www.eba.europa.eu/regulation-and-policy"),

        # DORA / NIS2 / GDPR / ePrivacy
        ("dora threat-led".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32022R2554"),
        ("tlpt".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32022R2554"),
        ("dora".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32022R2554"),
        ("nis2".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32022L2555"),
        ("gdpr".split(), "https://gdpr.eu/"),
        ("eprivacy".split(), "https://digital-strategy.ec.europa.eu/en/policies/eprivacy-directive"),
        ("cookie law".split(), "https://digital-strategy.ec.europa.eu/en/policies/eprivacy-directive"),
        ("whistleblower".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32019L1937"),
        ("2019/1937".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32019L1937"),

        # Tax
        ("dac7".split(), "https://taxation-customs.ec.europa.eu/taxation/tax-cooperation-control/administrative-cooperation/enhanced-administrative-cooperation-field-direct-taxation/dac7_en"),
        ("dac6".split(), "https://taxation-customs.ec.europa.eu/taxation/tax-cooperation-control/administrative-cooperation/enhanced-administrative-cooperation-field-direct-taxation/dac6_en"),
        ("dac4".split(), "https://taxation-customs.ec.europa.eu/taxation/tax-cooperation-control/administrative-cooperation_en"),
        ("country-by-country".split(), "https://taxation-customs.ec.europa.eu/taxation/tax-cooperation-control/administrative-cooperation_en"),
        ("common reporting standard".split(), "https://www.oecd.org/tax/automatic-exchange/common-reporting-standard/"),
        ("dac2".split(), "https://www.oecd.org/tax/automatic-exchange/common-reporting-standard/"),
        ("one-stop-shop".split(), "https://taxation-customs.ec.europa.eu/business/vat/oss_en"),
        ("import one-stop-shop".split(), "https://taxation-customs.ec.europa.eu/business/vat/ioss_en"),

        # Indirect tax
        ("vat returns".split(), "https://taxation-customs.ec.europa.eu/taxation/value-added-tax-vat_en"),
        ("ec sales".split(), "https://taxation-customs.ec.europa.eu/taxation/value-added-tax-vat_en"),
        ("intrastat".split(), "https://ec.europa.eu/eurostat/web/international-trade-in-goods/methodology/intrastat"),

        # Corporate / consumer
        ("corporate income tax".split(), "https://taxation-customs.ec.europa.eu/taxation/business-taxation_en"),
        ("annual accounts".split(), "https://commission.europa.eu/business-economy-euro/banking-and-finance/financial-supervision-and-risk-management/anti-money-laundering-and-countering-financing-terrorism_en"),
        ("ubo".split(), "https://commission.europa.eu/business-economy-euro/banking-and-finance/financial-supervision-and-risk-management/anti-money-laundering-and-countering-financing-terrorism_en"),
        ("complaints report".split(), "https://commission.europa.eu/info/business-economy-euro/banking-and-finance/consumer-finance-and-payments_en"),
        ("bop".split(), "https://www.ecb.europa.eu/stats/balance_of_payments_and_external/balance_of_payments/html/index.en.html"),
        ("balance-of-payments".split(), "https://www.ecb.europa.eu/stats/balance_of_payments_and_external/balance_of_payments/html/index.en.html"),

        # Generic FIU report — last in EU block.
        ("national fiu".split(), "https://commission.europa.eu/business-economy-euro/banking-and-finance/financial-supervision-and-risk-management/anti-money-laundering-and-countering-financing-terrorism_en"),
        ("suspicious transaction".split(), "https://commission.europa.eu/business-economy-euro/banking-and-finance/financial-supervision-and-risk-management/anti-money-laundering-and-countering-financing-terrorism_en"),

        # Fallbacks
        (["eba"], "https://www.eba.europa.eu/"),
    ],

    # -------------------------------------------------------------------
    # UAE — CBUAE, FTA, DIFC, ADGM, goAML, MoE, MoF, MOHRE
    # -------------------------------------------------------------------
    "uae": [
        ("svf".split(), "https://www.centralbank.ae/en/our-operations/regulations-and-supervision/"),
        ("rpscs".split(), "https://www.centralbank.ae/en/our-operations/regulations-and-supervision/"),
        ("stored value facility".split(), "https://www.centralbank.ae/en/our-operations/regulations-and-supervision/"),
        ("retail payment services".split(), "https://www.centralbank.ae/en/our-operations/regulations-and-supervision/"),
        ("cbuae regulatory returns".split(), "https://www.centralbank.ae/en/our-operations/regulations-and-supervision/"),
        ("form 19".split(), "https://www.centralbank.ae/en/our-operations/regulations-and-supervision/"),
        ("cbuae remittance".split(), "https://www.centralbank.ae/en/our-operations/regulations-and-supervision/"),
        ("dfsa".split(), "https://www.dfsa.ae/"),
        ("fsra".split(), "https://www.adgm.com/operating-in-adgm/post-registration-services/annual-filings/financial-services-regulatory-authority"),
        ("difc".split(), "https://www.difc.com/business/regulatory-laws/"),
        ("adgm".split(), "https://www.adgm.com/operating-in-adgm/post-registration-services/annual-filings"),

        # AML / sanctions
        ("goaml".split(), "https://www.uaefiu.gov.ae/en/"),
        ("str".split(), "https://www.uaefiu.gov.ae/en/"),
        ("sar".split(), "https://www.uaefiu.gov.ae/en/"),
        ("aml/cft annual".split(), "https://www.uaefiu.gov.ae/en/"),
        ("terrorist list".split(), "https://www.uaeiec.gov.ae/en-us/"),
        ("executive office".split(), "https://www.uaeiec.gov.ae/en-us/"),

        # Tax (FTA)
        ("corporate tax".split(), "https://www.tax.gov.ae/en/taxes/corporate.tax.aspx"),
        ("vat201".split(), "https://www.tax.gov.ae/en/taxes/vat.aspx"),
        ("vat return".split(), "https://www.tax.gov.ae/en/taxes/vat.aspx"),
        ("ex201".split(), "https://www.tax.gov.ae/en/taxes/excise.tax.aspx"),
        ("excise".split(), "https://www.tax.gov.ae/en/taxes/excise.tax.aspx"),
        ("master file".split(), "https://www.tax.gov.ae/en/taxes/corporate.tax.aspx"),
        ("local file".split(), "https://www.tax.gov.ae/en/taxes/corporate.tax.aspx"),
        ("trc".split(), "https://www.tax.gov.ae/en/services/tax.residency.certificate.aspx"),
        ("tax residency".split(), "https://www.tax.gov.ae/en/services/tax.residency.certificate.aspx"),

        # ESR / UBO / Trade
        ("esr".split(), "https://mof.gov.ae/economic-substance-regulations/"),
        ("economic substance".split(), "https://mof.gov.ae/economic-substance-regulations/"),
        ("ubo".split(), "https://www.economy.gov.ae/english/Pages/UBO.aspx"),
        ("trade licence".split(), "https://u.ae/en/information-and-services/business/doing-business-on-the-mainland/business-licences-in-uae"),

        # Data / cyber
        ("pdpl".split(), "https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws"),
        ("federal pdpl".split(), "https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws"),
        ("difc data protection".split(), "https://www.difc.com/business/operating/data-protection/"),
        ("adgm data protection".split(), "https://www.adgm.com/operating-in-adgm/office-of-data-protection"),
        ("nesa".split(), "https://www.tdra.gov.ae/en/about-tdra/uae-information-assurance-standards.aspx"),
        ("information assurance".split(), "https://www.tdra.gov.ae/en/about-tdra/uae-information-assurance-standards.aspx"),
        ("ia standards".split(), "https://www.tdra.gov.ae/en/about-tdra/uae-information-assurance-standards.aspx"),
        ("sia".split(), "https://www.tdra.gov.ae/en/about-tdra/uae-information-assurance-standards.aspx"),

        # Labour
        ("wages protection".split(), "https://mohre.gov.ae/en/our-services/wages-protection-system.aspx"),
        ("nafis".split(), "https://nafis.gov.ae/"),
        ("emiratisation".split(), "https://nafis.gov.ae/"),
        ("mohre".split(), "https://mohre.gov.ae/"),
        ("gpssa".split(), "https://www.gpssa.gov.ae/en/Pages/default.aspx"),

        # Consumer
        ("sanadak".split(), "https://www.sanadak.gov.ae/"),

        # Fallback
        (["cbuae"], "https://www.centralbank.ae/en/"),
        (["fta"], "https://www.tax.gov.ae/"),
    ],

    # -------------------------------------------------------------------
    # Singapore — MAS, ACRA, IRAS, STRO, MOM, CPF, SkillsFuture, PDPC
    # -------------------------------------------------------------------
    "singapore": [
        # MAS / payments
        ("ps act".split(), "https://www.mas.gov.sg/regulation/payments/payment-services-act"),
        ("mpi".split(), "https://www.mas.gov.sg/regulation/payments/payment-services-act"),
        ("major payment institution".split(), "https://www.mas.gov.sg/regulation/payments/payment-services-act"),
        ("ps-n02".split(), "https://www.mas.gov.sg/regulation/notices/notice-psn-n02"),
        ("psn01".split(), "https://www.mas.gov.sg/regulation/notices/psn01"),
        ("psn02".split(), "https://www.mas.gov.sg/regulation/notices/psn02"),
        ("psn06".split(), "https://www.mas.gov.sg/regulation/notices/psn06"),
        ("trm guidelines".split(), "https://www.mas.gov.sg/regulation/guidelines/technology-risk-management-guidelines"),
        ("notice 644".split(), "https://www.mas.gov.sg/regulation/notices/notice-644"),
        ("outsourcing".split(), "https://www.mas.gov.sg/regulation/guidelines/guidelines-on-outsourcing"),
        ("fair dealing".split(), "https://www.mas.gov.sg/regulation/guidelines/guidelines-on-fair-dealing"),
        ("cyber hygiene".split(), "https://www.mas.gov.sg/regulation/notices/notice-on-cyber-hygiene"),

        # AML / STRO
        ("stro".split(), "https://www.police.gov.sg/Advisories/Crime/Commercial-Crimes/Suspicious-Transaction-Reporting-Office"),
        ("str".split(), "https://www.police.gov.sg/Advisories/Crime/Commercial-Crimes/Suspicious-Transaction-Reporting-Office"),
        ("un sanctions".split(), "https://www.mas.gov.sg/regulation/anti-money-laundering"),

        # IRAS / tax
        ("gst form 5".split(), "https://www.iras.gov.sg/taxes/goods-services-tax-(gst)/gst-rate-change/gst-returns/filing-your-gst-return-(form-5)"),
        ("form c".split(), "https://www.iras.gov.sg/taxes/corporate-income-tax/filing/form-c-s-form-c-s-(lite)-form-c"),
        ("eci".split(), "https://www.iras.gov.sg/taxes/corporate-income-tax/filing/estimated-chargeable-income-eci"),
        ("ir37".split(), "https://www.iras.gov.sg/taxes/withholding-tax/payments-to-non-resident-company/withholding-tax-on-payments-to-non-resident-companies"),
        ("ir8a".split(), "https://www.iras.gov.sg/taxes/individual-income-tax/employees/auto-inclusion-scheme-(ais)-for-employment-income/about-auto-inclusion-scheme-(ais)-for-employment-income"),
        ("iras tp".split(), "https://www.iras.gov.sg/taxes/corporate-income-tax/specific-topics/transfer-pricing"),
        ("iras crs".split(), "https://www.iras.gov.sg/taxes/international-tax/common-reporting-standard-(crs)"),

        # CPF / MOM
        ("cpf".split(), "https://www.cpf.gov.sg/employer"),
        ("ir21".split(), "https://www.iras.gov.sg/taxes/individual-income-tax/employees/leaving-singapore/tax-clearance-for-employees"),
        ("mom work pass".split(), "https://www.mom.gov.sg/passes-and-permits"),
        ("ep ".split(), "https://www.mom.gov.sg/passes-and-permits/employment-pass"),
        ("skills development levy".split(), "https://www.skillsfuture.gov.sg/sdl"),
        ("sdl".split(), "https://www.skillsfuture.gov.sg/sdl"),

        # ACRA
        ("annual return".split(), "https://www.acra.gov.sg/how-to-guides/filing-annual-returns"),
        ("acra".split(), "https://www.acra.gov.sg/"),
        ("registrable controllers".split(), "https://www.acra.gov.sg/how-to-guides/setting-up-a-local-company/keeping-your-information-with-acra-up-to-date"),

        # PDPA
        ("pdpa".split(), "https://www.pdpc.gov.sg/Overview-of-PDPA/The-Legislation/Personal-Data-Protection-Act"),

        # Fallback
        (["mas"], "https://www.mas.gov.sg/regulation"),
        (["iras"], "https://www.iras.gov.sg/"),
    ],

    # -------------------------------------------------------------------
    # Canada — FinTRAC, CRA, Revenu Québec, OSFI, OPC, provinces
    # -------------------------------------------------------------------
    "canada": [
        # FinTRAC
        ("fintrac msb".split(), "https://fintrac-canafe.canada.ca/msb-esm/registration-inscription/intro-eng"),
        ("amf money-services".split(), "https://lautorite.qc.ca/en/professionals/money-services-business-licence-applicants"),
        ("provincial msb".split(), "https://fintrac-canafe.canada.ca/msb-esm/intro-eng"),
        ("fintrac suspicious".split(), "https://fintrac-canafe.canada.ca/reporting-declaration/Info/str-eng"),
        ("large cash transaction".split(), "https://fintrac-canafe.canada.ca/reporting-declaration/Info/lctr-eng"),
        ("lctr".split(), "https://fintrac-canafe.canada.ca/reporting-declaration/Info/lctr-eng"),
        ("electronic funds transfer".split(), "https://fintrac-canafe.canada.ca/reporting-declaration/Info/eftr-eng"),
        ("eftr".split(), "https://fintrac-canafe.canada.ca/reporting-declaration/Info/eftr-eng"),
        ("large virtual currency".split(), "https://fintrac-canafe.canada.ca/reporting-declaration/Info/lvctr-eng"),
        ("lvctr".split(), "https://fintrac-canafe.canada.ca/reporting-declaration/Info/lvctr-eng"),
        ("compliance effectiveness review".split(), "https://fintrac-canafe.canada.ca/guidance-directives/compliance-conformite/Guide4/4-eng"),

        # OSFI / sanctions
        ("osfi".split(), "https://www.osfi-bsif.gc.ca/Eng/fi-if/amlc-clrpc/Pages/default.aspx"),

        # CRA / tax
        ("t2".split(), "https://www.canada.ca/en/revenue-agency/services/forms-publications/forms/t2.html"),
        ("co-17".split(), "https://www.revenuquebec.ca/en/businesses/income-tax/corporations/"),
        ("gst/hst".split(), "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses.html"),
        ("gst34".split(), "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses.html"),
        ("qst".split(), "https://www.revenuquebec.ca/en/businesses/consumption-taxes/gsthst-and-qst/"),
        ("vdz-441".split(), "https://www.revenuquebec.ca/en/businesses/consumption-taxes/gsthst-and-qst/"),
        ("bc pst".split(), "https://www2.gov.bc.ca/gov/content/taxes/sales-taxes/pst"),
        ("sk pst".split(), "https://www.sets.saskatchewan.ca/rptp/portal/home/pst"),
        ("mb rst".split(), "https://www.gov.mb.ca/finance/taxation/taxes/retail.html"),
        ("pd7a".split(), "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/payroll/remit-pay-payroll-deductions/how-make-payment.html"),
        ("payroll source deductions".split(), "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/payroll/remit-pay-payroll-deductions/how-make-payment.html"),
        ("t4".split(), "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/payroll/completing-filing-information-returns/t4-information-employers.html"),
        ("rl-1".split(), "https://www.revenuquebec.ca/en/businesses/source-deductions-and-employer-contributions/declaring-source-deductions-and-employer-contributions/"),
        ("eht".split(), "https://www.ontario.ca/page/employer-health-tax-eht"),
        ("ontario employer health".split(), "https://www.ontario.ca/page/employer-health-tax-eht"),
        ("canada pension plan".split(), "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/payroll.html"),
        ("qpp".split(), "https://www.revenuquebec.ca/en/citizens/your-situation/new-residents/canada-pension-plan-and-quebec-pension-plan/"),
        ("employment insurance".split(), "https://www.canada.ca/en/employment-social-development/programs/ei.html"),
        ("wsib".split(), "https://www.wsib.ca/en"),
        ("cnesst".split(), "https://www.cnesst.gouv.qc.ca/en"),
        ("t5".split(), "https://www.canada.ca/en/revenue-agency/services/forms-publications/forms/t5.html"),
        ("nr4".split(), "https://www.canada.ca/en/revenue-agency/services/forms-publications/forms/nr4.html"),
        ("t1135".split(), "https://www.canada.ca/en/revenue-agency/services/forms-publications/forms/t1135.html"),
        ("fatca part xviii".split(), "https://www.canada.ca/en/revenue-agency/services/tax/international-non-residents/enhanced-financial-account-information-reporting.html"),
        ("part xix".split(), "https://www.canada.ca/en/revenue-agency/services/tax/international-non-residents/enhanced-financial-account-information-reporting.html"),

        # Unclaimed / corporate
        ("quebec unclaimed".split(), "https://www.revenuquebec.ca/en/unclaimed-property/"),
        ("alberta unclaimed".split(), "https://unclaimedproperty.alberta.ca/"),
        ("bc unclaimed".split(), "https://www.unclaimedpropertybc.ca/"),
        ("form 22".split(), "https://www.ic.gc.ca/eic/site/cd-dgc.nsf/eng/cs01180.html"),
        ("corporations canada".split(), "https://www.ic.gc.ca/eic/site/cd-dgc.nsf/eng/home"),
        ("provincial corporate annual".split(), "https://www.ic.gc.ca/eic/site/cd-dgc.nsf/eng/home"),

        # Privacy
        ("pipeda".split(), "https://www.priv.gc.ca/en/privacy-topics/privacy-laws-in-canada/the-personal-information-protection-and-electronic-documents-act-pipeda/"),
        ("quebec law 25".split(), "https://www.cai.gouv.qc.ca/english/"),
        ("law 25".split(), "https://www.cai.gouv.qc.ca/english/"),

        # Statistics
        ("bank of canada".split(), "https://www.statcan.gc.ca/en/survey/business"),
        ("international transactions survey".split(), "https://www.statcan.gc.ca/en/survey/business"),
        ("statistics canada".split(), "https://www.statcan.gc.ca/en/survey/business"),

        # Fallback
        (["fintrac"], "https://fintrac-canafe.canada.ca/intro-eng"),
        (["cra"], "https://www.canada.ca/en/revenue-agency.html"),
    ],

    # -------------------------------------------------------------------
    # Lithuania — Bank of Lithuania, VMI, Sodra, FCIS, NKSC
    # -------------------------------------------------------------------
    "lithuania": [
        # BoL / payments
        ("bank of lithuania e-money".split(), "https://www.lb.lt/en/sfi-financial-market-participants/electronic-money-institutions-and-payment-institutions"),
        ("payment institution".split(), "https://www.lb.lt/en/sfi-financial-market-participants/electronic-money-institutions-and-payment-institutions"),
        ("e-money institution".split(), "https://www.lb.lt/en/sfi-financial-market-participants/electronic-money-institutions-and-payment-institutions"),
        ("own-funds".split(), "https://www.lb.lt/en/sfi-financial-market-participants/electronic-money-institutions-and-payment-institutions"),
        ("bol periodic".split(), "https://www.lb.lt/en/sfi-financial-market-participants/electronic-money-institutions-and-payment-institutions"),
        ("safeguarding audit".split(), "https://www.lb.lt/en/sfi-financial-market-participants/electronic-money-institutions-and-payment-institutions"),
        ("anacredit".split(), "https://www.ecb.europa.eu/stats/money_credit_banking/anacredit/html/index.en.html"),
        ("bop survey".split(), "https://www.lb.lt/en/statistics"),
        ("balance-of-payments survey".split(), "https://www.lb.lt/en/statistics"),
        ("monetary financial statistics".split(), "https://www.lb.lt/en/statistics"),

        # AML / FCIS
        ("fcis".split(), "https://fntt.lt/en/"),
        ("str threshold".split(), "https://fntt.lt/en/"),
        ("mlro".split(), "https://fntt.lt/en/"),
        ("ml/tf".split(), "https://fntt.lt/en/"),
        ("sanctions".split(), "https://www.urm.lt/default/en/foreign-policy/international-restrictive-measures-sanctions"),

        # VMI / tax
        ("pln204".split(), "https://www.vmi.lt/evmi/en"),
        ("cit return".split(), "https://www.vmi.lt/evmi/en"),
        ("fr0600".split(), "https://www.vmi.lt/evmi/en"),
        ("vat return".split(), "https://www.vmi.lt/evmi/en"),
        ("fr0564".split(), "https://www.vmi.lt/evmi/en"),
        ("ec sales".split(), "https://www.vmi.lt/evmi/en"),
        ("intrastat".split(), "https://osp.stat.gov.lt/intrastatas"),
        ("vmi crs".split(), "https://www.vmi.lt/evmi/en"),
        ("fr0573".split(), "https://www.vmi.lt/evmi/en"),
        ("gpm313".split(), "https://www.vmi.lt/evmi/en"),
        ("gpm".split(), "https://www.vmi.lt/evmi/en"),
        ("transfer pricing".split(), "https://www.vmi.lt/evmi/en"),
        ("one-stop-shop".split(), "https://www.vmi.lt/evmi/en"),

        # Social / pensions
        ("sodra".split(), "https://www.sodra.lt/en"),
        ("pillar iii".split(), "https://www.sodra.lt/en"),

        # EU passthroughs
        ("travel rule".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32023R1113"),
        ("dac6".split(), "https://www.vmi.lt/evmi/en"),
        ("dac4".split(), "https://www.vmi.lt/evmi/en"),
        ("eba fraud".split(), "https://www.eba.europa.eu/regulation-and-policy/payment-services-and-electronic-money"),
        ("dora".split(), "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32022R2554"),
        ("gdpr".split(), "https://vdai.lrv.lt/en"),

        # Cyber
        ("nksc".split(), "https://www.nksc.lt/en/"),
        ("cyber-incident".split(), "https://www.nksc.lt/en/"),

        # Companies registry / UBO
        ("jadis".split(), "https://www.registrucentras.lt/p/1094"),
        ("centre of registers".split(), "https://www.registrucentras.lt/p/1094"),
        ("jangis".split(), "https://www.registrucentras.lt/p/1094"),
        ("ubo".split(), "https://www.registrucentras.lt/p/1094"),

        # Consumer
        ("vvtat".split(), "https://www.vvtat.lt/en"),
        ("consumer rights".split(), "https://www.vvtat.lt/en"),

        # Fallbacks
        (["bol"], "https://www.lb.lt/en/"),
        (["vmi"], "https://www.vmi.lt/evmi/en"),
    ],
}


def find_source_url(jurisdiction_code: str, form_name: str) -> Optional[str]:
    """Return the first curated URL whose tokens all appear in form_name."""
    if not form_name:
        return None
    needle = form_name.lower()
    for tokens, url in _HINTS.get(jurisdiction_code, []):
        if all(t.lower() in needle for t in tokens):
            return url
    return None
