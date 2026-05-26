"""Curated regulator source URLs for the most common filings.

Each entry is a list of `(needles, url)` pairs scoped to one jurisdiction.
We match by checking whether ALL needle tokens appear in the rule's
form_name (case-insensitive). First match wins. This deliberately favours
authority-level landing pages (e.g. HMRC's VAT guide, MCA's home) over
hyper-specific form URLs — the goal is "click to start", not "directly
download the PDF".

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
    # India — RBI, MCA, GST, Income Tax, FIU-IND
    # -------------------------------------------------------------------
    "india": [
        (["gstr-3b"], "https://www.gst.gov.in/help/returns"),
        (["gstr-1"], "https://www.gst.gov.in/help/returns"),
        (["gstr"], "https://www.gst.gov.in/help/returns"),
        (["gst", "annual"], "https://www.gst.gov.in/help/returns/annualreturns"),
        (["gst"], "https://www.gst.gov.in/"),
        (["fla"], "https://flair.rbi.org.in/"),
        (["fc-gpr"], "https://firms.rbi.org.in/"),
        (["fc-trs"], "https://firms.rbi.org.in/"),
        (["odi"], "https://firms.rbi.org.in/"),
        (["apr"], "https://firms.rbi.org.in/"),
        (["xbrl", "rbi"], "https://www.rbi.org.in/Scripts/bs_viewcontent.aspx?Id=4140"),
        (["str"], "https://fiuindia.gov.in/"),
        (["ctr"], "https://fiuindia.gov.in/"),
        (["pmla"], "https://fiuindia.gov.in/"),
        (["tds", "26q"], "https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing/tds"),
        (["tds"], "https://www.incometax.gov.in/iec/foportal/"),
        (["form 26as"], "https://www.incometax.gov.in/"),
        (["itr"], "https://www.incometax.gov.in/iec/foportal/"),
        (["advance tax"], "https://www.incometax.gov.in/iec/foportal/help/all-topics/payment-of-taxes"),
        (["transfer pricing"], "https://www.incometax.gov.in/"),
        (["sft"], "https://www.incometax.gov.in/"),
        (["aoc-4"], "https://www.mca.gov.in/MinistryV2/companyformsdownload.html"),
        (["mgt-7"], "https://www.mca.gov.in/MinistryV2/companyformsdownload.html"),
        (["dpt-3"], "https://www.mca.gov.in/MinistryV2/companyformsdownload.html"),
        (["msme", "form"], "https://www.mca.gov.in/"),
        (["pf", "epfo"], "https://www.epfindia.gov.in/"),
        (["esi"], "https://www.esic.in/"),
        (["professional tax"], "https://www.shramsuvidha.gov.in/"),
        (["dpdp"], "https://www.meity.gov.in/data-protection-framework"),
        (["cert-in"], "https://www.cert-in.org.in/"),
        (["rbi"], "https://www.rbi.org.in/"),
        (["mca"], "https://www.mca.gov.in/"),
    ],

    # -------------------------------------------------------------------
    # United States — FinCEN, IRS, OFAC, SEC, state
    # -------------------------------------------------------------------
    "us": [
        (["fincen", "boi"], "https://www.fincen.gov/boi"),
        (["beneficial ownership"], "https://www.fincen.gov/boi"),
        (["fincen", "ctr"], "https://www.fincen.gov/resources/filing-information"),
        (["fincen", "sar"], "https://www.fincen.gov/resources/filing-information"),
        (["fincen", "112"], "https://www.fincen.gov/resources/filing-information"),
        (["fincen", "111"], "https://www.fincen.gov/resources/filing-information"),
        (["form 8300"], "https://www.irs.gov/businesses/small-businesses-self-employed/form-8300-and-reporting-cash-payments-of-over-10000"),
        (["bsa", "aml"], "https://www.fincen.gov/resources/statutes-and-regulations/bank-secrecy-act"),
        (["ofac"], "https://ofac.treasury.gov/"),
        (["sanctions"], "https://ofac.treasury.gov/"),
        (["form 1120"], "https://www.irs.gov/forms-pubs/about-form-1120"),
        (["form 941"], "https://www.irs.gov/forms-pubs/about-form-941"),
        (["form 940"], "https://www.irs.gov/forms-pubs/about-form-940"),
        (["form w-2"], "https://www.irs.gov/forms-pubs/about-form-w-2"),
        (["form 1099"], "https://www.irs.gov/forms-pubs/about-form-1099-misc"),
        (["delaware", "franchise"], "https://corp.delaware.gov/paytaxes/"),
        (["delaware", "annual"], "https://corp.delaware.gov/paytaxes/"),
        (["sales tax"], "https://www.irs.gov/businesses/small-businesses-self-employed/state-government-websites"),
        (["money transmitter"], "https://www.csbs.org/nationwide-multistate-licensing-system-nmls"),
        (["nmls"], "https://www.csbs.org/nationwide-multistate-licensing-system-nmls"),
        (["fincen"], "https://www.fincen.gov/"),
        (["irs"], "https://www.irs.gov/"),
    ],

    # -------------------------------------------------------------------
    # United Kingdom — HMRC, Companies House, FCA, ICO
    # -------------------------------------------------------------------
    "uk": [
        (["vat", "return"], "https://www.gov.uk/vat-returns"),
        (["vat"], "https://www.gov.uk/topic/business-tax/vat"),
        (["corporation tax", "ct600"], "https://www.gov.uk/government/publications/corporation-tax-company-tax-return-ct600-2008-version-2"),
        (["corporation tax"], "https://www.gov.uk/corporation-tax"),
        (["paye"], "https://www.gov.uk/paye-for-employers"),
        (["companies house"], "https://www.gov.uk/government/organisations/companies-house"),
        (["confirmation statement"], "https://www.gov.uk/file-an-annual-return-with-companies-house"),
        (["psc", "register"], "https://www.gov.uk/government/publications/guidance-to-the-people-with-significant-control-requirements-for-companies-and-limited-liability-partnerships"),
        (["fca", "rep"], "https://www.handbook.fca.org.uk/handbook/SUP/16/"),
        (["fca"], "https://www.fca.org.uk/firms/regulatory-reporting"),
        (["fin"], "https://www.fca.org.uk/firms/regulatory-reporting"),
        (["mlro"], "https://www.fca.org.uk/firms/financial-crime"),
        (["sar", "nca"], "https://www.nationalcrimeagency.gov.uk/what-we-do/crime-threats/money-laundering-and-illicit-finance/suspicious-activity-reports"),
        (["ico", "gdpr"], "https://ico.org.uk/for-organisations/"),
        (["gdpr"], "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/"),
        (["intrastat"], "https://www.gov.uk/intrastat"),
        (["hmrc"], "https://www.gov.uk/government/organisations/hm-revenue-customs"),
    ],

    # -------------------------------------------------------------------
    # European Union
    # -------------------------------------------------------------------
    "eu": [
        (["psd2"], "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32015L2366"),
        (["psd3"], "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A52023PC0367"),
        (["eba", "rep"], "https://www.eba.europa.eu/risk-and-data-analysis/reporting-frameworks"),
        (["eba"], "https://www.eba.europa.eu/"),
        (["dora"], "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32022R2554"),
        (["nis2"], "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32022L2555"),
        (["gdpr"], "https://gdpr.eu/"),
        (["travel rule"], "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32023R1113"),
        (["dac7"], "https://taxation-customs.ec.europa.eu/taxation/tax-cooperation-control/administrative-cooperation/enhanced-administrative-cooperation-field-direct-taxation/dac7_en"),
        (["vat"], "https://taxation-customs.ec.europa.eu/taxation/value-added-tax-vat_en"),
        (["intrastat", "ec sales"], "https://ec.europa.eu/eurostat/web/international-trade-in-goods/methodology/intrastat"),
        (["ubo"], "https://commission.europa.eu/business-economy-euro/banking-and-finance/financial-supervision-and-risk-management/anti-money-laundering-and-countering-financing-terrorism_en"),
    ],

    # -------------------------------------------------------------------
    # UAE — Central Bank, FTA, ADGM, DIFC, goAML
    # -------------------------------------------------------------------
    "uae": [
        (["corporate tax"], "https://www.tax.gov.ae/en/taxes/corporate.tax.aspx"),
        (["vat", "return"], "https://www.tax.gov.ae/en/taxes/vat.aspx"),
        (["vat"], "https://www.tax.gov.ae/en/taxes/vat.aspx"),
        (["str", "goaml"], "https://www.uaefiu.gov.ae/en/"),
        (["goaml"], "https://www.uaefiu.gov.ae/en/"),
        (["esr"], "https://mof.gov.ae/economic-substance-regulations/"),
        (["ubo"], "https://mohre.gov.ae/"),
        (["central bank"], "https://www.centralbank.ae/en/"),
        (["adgm"], "https://www.adgm.com/"),
        (["difc"], "https://www.difc.com/"),
        (["dmcc"], "https://www.dmcc.ae/"),
        (["fta"], "https://www.tax.gov.ae/"),
    ],

    # -------------------------------------------------------------------
    # Singapore — MAS, ACRA, IRAS, STRO
    # -------------------------------------------------------------------
    "singapore": [
        (["str", "stro"], "https://www.police.gov.sg/Advisories/Crime/Commercial-Crimes/Suspicious-Transaction-Reporting-Office"),
        (["str"], "https://www.police.gov.sg/Advisories/Crime/Commercial-Crimes/Suspicious-Transaction-Reporting-Office"),
        (["gst", "return"], "https://www.iras.gov.sg/taxes/goods-services-tax-(gst)"),
        (["gst"], "https://www.iras.gov.sg/taxes/goods-services-tax-(gst)"),
        (["form c", "iras"], "https://www.iras.gov.sg/taxes/corporate-income-tax"),
        (["corporate income tax"], "https://www.iras.gov.sg/taxes/corporate-income-tax"),
        (["acra"], "https://www.acra.gov.sg/"),
        (["annual return", "acra"], "https://www.acra.gov.sg/how-to-guides/filing-annual-returns"),
        (["mas"], "https://www.mas.gov.sg/regulation"),
        (["pdpa"], "https://www.pdpc.gov.sg/"),
    ],

    # -------------------------------------------------------------------
    # Canada — CRA, FINTRAC, OSFI
    # -------------------------------------------------------------------
    "canada": [
        (["fintrac"], "https://fintrac-canafe.canada.ca/intro-eng"),
        (["gst", "hst"], "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses.html"),
        (["t2"], "https://www.canada.ca/en/revenue-agency/services/forms-publications/forms/t2.html"),
        (["cra"], "https://www.canada.ca/en/revenue-agency.html"),
        (["osfi"], "https://www.osfi-bsif.gc.ca/Eng/Pages/default.aspx"),
    ],

    # -------------------------------------------------------------------
    # Lithuania — Bank of Lithuania, VMI, FNTT
    # -------------------------------------------------------------------
    "lithuania": [
        (["bank of lithuania"], "https://www.lb.lt/en/"),
        (["fntt"], "https://fntt.lt/en/"),
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
