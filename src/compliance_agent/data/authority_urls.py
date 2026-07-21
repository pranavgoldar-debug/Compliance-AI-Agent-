"""Authority → primary URL mapping.

Used to backfill Rule.source_url on existing rules whose URL is empty.
The strings here match the `authority` field on FintechFiling rows in
compliance_agent.fintech.* — case-insensitive substring match.

Order matters: longer / more specific keys come first so e.g. "FCA / HMRC"
hits "FCA / HMRC" before falling back to just "FCA". Lookup logic is
greedy first-match.

Add new entries when seeding a new jurisdiction. Manual per-rule override
via the Compliance Rules edit dialog always wins over this lookup —
the backfill CLI never overwrites a URL that's already set.
"""
from __future__ import annotations


# Ordered list of (authority-substring, primary-url) tuples. Longest /
# most specific patterns first.
AUTHORITY_URLS: list[tuple[str, str]] = [
    # --- India --------------------------------------------------------
    ("Income Tax Department", "https://www.incometax.gov.in/iec/foportal/"),
    ("Ministry of Corporate Affairs", "https://www.mca.gov.in/"),
    ("MCA", "https://www.mca.gov.in/"),
    ("RBI (FED)", "https://www.rbi.org.in/Scripts/BS_FemaNotifications.aspx"),
    ("RBI", "https://www.rbi.org.in/"),
    ("FIU-IND", "https://fiuindia.gov.in/"),
    ("FIU", "https://fiuindia.gov.in/"),
    ("GSTN", "https://www.gst.gov.in/"),
    ("CBIC", "https://www.cbic.gov.in/"),
    ("CBDT", "https://incometaxindia.gov.in/"),
    ("EPFO", "https://www.epfindia.gov.in/site_en/"),
    ("ESIC", "https://www.esic.gov.in/"),
    ("SEBI", "https://www.sebi.gov.in/"),
    ("IRDAI", "https://www.irdai.gov.in/"),
    ("IFSCA", "https://ifsca.gov.in/"),
    ("MEA", "https://www.mea.gov.in/"),
    ("MeitY", "https://www.meity.gov.in/"),
    ("CERT-In", "https://www.cert-in.org.in/"),
    ("NPCI", "https://www.npci.org.in/"),
    ("Telangana Labour Department", "https://labour.telangana.gov.in/"),
    ("Karnataka Labour Department", "https://labour.karnataka.gov.in/"),
    # --- UAE ----------------------------------------------------------
    ("CBUAE", "https://www.centralbank.ae/"),
    ("DFSA (DIFC)", "https://www.dfsa.ae/"),
    ("DFSA", "https://www.dfsa.ae/"),
    ("FSRA (ADGM)", "https://www.adgm.com/fsra"),
    ("FSRA", "https://www.adgm.com/fsra"),
    ("UAE FIU", "https://www.uaefiu.gov.ae/"),
    ("Executive Office for Control & Non-Proliferation", "https://www.uaeiec.gov.ae/"),
    ("Executive Office", "https://www.uaeiec.gov.ae/"),
    ("Ministry of Economy", "https://www.moec.gov.ae/"),
    ("Federal Tax Authority", "https://tax.gov.ae/en/"),
    ("FTA", "https://tax.gov.ae/en/"),
    ("DMCC", "https://www.dmcc.ae/"),
    ("DIFC", "https://www.difc.ae/"),
    ("ADGM", "https://www.adgm.com/"),
    ("MoHRE", "https://www.mohre.gov.ae/"),
    ("GPSSA", "https://www.gpssa.gov.ae/en/Pages/default.aspx"),
    # --- UK -----------------------------------------------------------
    ("FCA / HMRC", "https://www.fca.org.uk/"),
    ("FCA", "https://www.fca.org.uk/"),
    ("HMRC", "https://www.gov.uk/government/organisations/hm-revenue-customs"),
    ("OFSI (HM Treasury)", "https://www.gov.uk/government/organisations/office-of-financial-sanctions-implementation"),
    ("OFSI", "https://www.gov.uk/government/organisations/office-of-financial-sanctions-implementation"),
    ("National Crime Agency", "https://www.nationalcrimeagency.gov.uk/"),
    ("NCA", "https://www.nationalcrimeagency.gov.uk/"),
    ("Companies House", "https://www.gov.uk/government/organisations/companies-house"),
    ("ICO", "https://ico.org.uk/"),
    ("Pensions Regulator", "https://www.thepensionsregulator.gov.uk/"),
    # --- US -----------------------------------------------------------
    ("FinCEN", "https://www.fincen.gov/"),
    ("OFAC", "https://ofac.treasury.gov/"),
    ("IRS", "https://www.irs.gov/"),
    ("SEC", "https://www.sec.gov/"),
    ("CFPB", "https://www.consumerfinance.gov/"),
    ("State MTL", "https://www.csbs.org/nationwide-multistate-licensing-system"),
    ("NMLS", "https://www.nmls.org/"),
    # --- EU -----------------------------------------------------------
    ("EBA", "https://www.eba.europa.eu/"),
    ("ECB", "https://www.ecb.europa.eu/"),
    ("ESMA", "https://www.esma.europa.eu/"),
    ("EDPB", "https://www.edpb.europa.eu/"),
    # --- Singapore ----------------------------------------------------
    ("MAS", "https://www.mas.gov.sg/"),
    ("IRAS", "https://www.iras.gov.sg/"),
    ("ACRA", "https://www.acra.gov.sg/"),
    # --- Canada -------------------------------------------------------
    ("FINTRAC", "https://fintrac-canafe.canada.ca/intro-eng"),
    ("CRA", "https://www.canada.ca/en/revenue-agency.html"),
    ("OSFI", "https://www.osfi-bsif.gc.ca/"),
    ("Innovation, Science and Economic Development", "https://www.canada.ca/en/innovation-science-economic-development.html"),
    # --- Lithuania ----------------------------------------------------
    ("Bank of Lithuania", "https://www.lb.lt/en/"),
    ("FNTT", "https://fntt.lt/en/home/"),
    ("VMI", "https://www.vmi.lt/evmi/"),
    ("Sodra", "https://www.sodra.lt/en"),
    # --- Card brands / industry bodies --------------------------------
    ("Card brands / acquirers", "https://www.pcisecuritystandards.org/"),
    ("PCI", "https://www.pcisecuritystandards.org/"),
]


def lookup(authority: str) -> str | None:
    """Return the best-match URL for an authority string, or None if no
    match. Case-insensitive substring search; longer keys take
    precedence (the list above is ordered most-specific-first).
    """
    if not authority:
        return None
    needle = authority.lower()
    for key, url in AUTHORITY_URLS:
        if key.lower() in needle:
            return url
    return None


__all__ = ["AUTHORITY_URLS", "lookup"]
