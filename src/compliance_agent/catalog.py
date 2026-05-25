"""Catalog of bundled regulations grouped by country.

Each regulation points at a text excerpt shipped with the package. The
mock extractor recognizes the markers in those files (see `mock.py`) and
returns curated requirements per regulation. When wired to the live API,
the same files will be re-extracted by Claude.
"""
from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class Regulation(BaseModel):
    id: str
    name: str
    short_name: str
    scope: str
    framework: Optional[str] = None
    text_resource: str  # relative path under compliance_agent/data/regulations/

    def read_text(self) -> str:
        path = files("compliance_agent.data.regulations").joinpath(self.text_resource)
        return Path(str(path)).read_text(encoding="utf-8")


class Country(BaseModel):
    code: str
    name: str
    flag: str
    regulations: list[Regulation]


CATALOG: list[Country] = [
    Country(
        code="india",
        name="India",
        flag="🇮🇳",
        regulations=[
            Regulation(
                id="india_dpdp_2023",
                name="Digital Personal Data Protection Act, 2023",
                short_name="DPDP Act 2023",
                scope="Applies to processing of digital personal data within India, or outside India in connection with offering goods or services to Data Principals in India.",
                framework="DPDP Act 2023",
                text_resource="india/dpdp_2023.txt",
            ),
            Regulation(
                id="india_cert_in_2022",
                name="CERT-In Cyber Security Directions, April 2022",
                short_name="CERT-In Directions 2022",
                scope="Applies to all service providers, intermediaries, data centres, body corporates and Government organisations operating in India.",
                framework="CERT-In 2022",
                text_resource="india/cert_in_2022.txt",
            ),
        ],
    ),
    Country(
        code="eu",
        name="European Union",
        flag="🇪🇺",
        regulations=[
            Regulation(
                id="eu_gdpr",
                name="General Data Protection Regulation (EU) 2016/679",
                short_name="GDPR",
                scope="Applies to processing of personal data of data subjects in the EU by controllers or processors established in the EU, or offering goods/services to or monitoring behaviour of data subjects in the EU.",
                framework="GDPR",
                text_resource="eu/gdpr.txt",
            ),
            Regulation(
                id="eu_nis2",
                name="NIS2 Directive (EU) 2022/2555",
                short_name="NIS2",
                scope="Applies to essential and important entities across critical sectors (energy, transport, banking, health, digital infrastructure, public administration, etc.) operating in the EU.",
                framework="NIS2",
                text_resource="eu/nis2.txt",
            ),
        ],
    ),
    Country(
        code="us",
        name="United States",
        flag="🇺🇸",
        regulations=[
            Regulation(
                id="us_hipaa",
                name="Health Insurance Portability and Accountability Act",
                short_name="HIPAA",
                scope="Applies to covered entities (health plans, healthcare clearinghouses, certain healthcare providers) and their business associates handling protected health information.",
                framework="HIPAA",
                text_resource="us/hipaa.txt",
            ),
            Regulation(
                id="us_ccpa",
                name="California Consumer Privacy Act (as amended by CPRA)",
                short_name="CCPA / CPRA",
                scope="Applies to for-profit businesses doing business in California that meet revenue, data-volume, or data-sales thresholds.",
                framework="CCPA",
                text_resource="us/ccpa.txt",
            ),
            Regulation(
                id="us_pci_dss",
                name="PCI DSS v4.0 (Payment Card Industry Data Security Standard)",
                short_name="PCI DSS v4.0",
                scope="Applies to all entities that store, process, or transmit cardholder data, and to entities that could impact the security of the cardholder data environment.",
                framework="PCI DSS v4.0",
                text_resource="us/pci_dss.txt",
            ),
        ],
    ),
    Country(
        code="uk",
        name="United Kingdom",
        flag="🇬🇧",
        regulations=[
            Regulation(
                id="uk_gdpr",
                name="UK GDPR and Data Protection Act 2018",
                short_name="UK GDPR + DPA 2018",
                scope="Applies to controllers and processors established in the UK, and to non-UK organisations offering goods/services to or monitoring data subjects in the UK.",
                framework="UK GDPR",
                text_resource="uk/uk_gdpr.txt",
            ),
        ],
    ),
    Country(
        code="uae",
        name="United Arab Emirates",
        flag="🇦🇪",
        regulations=[
            Regulation(
                id="uae_pdpl_2021",
                name="Federal Decree-Law No. 45 of 2021 (Personal Data Protection Law)",
                short_name="UAE PDPL 2021",
                scope="Applies to processing of personal data of UAE data subjects, whether the processing takes place inside or outside the State, with sector-specific exclusions.",
                framework="UAE PDPL",
                text_resource="uae/pdpl_2021.txt",
            ),
        ],
    ),
    Country(
        code="singapore",
        name="Singapore",
        flag="🇸🇬",
        regulations=[
            Regulation(
                id="singapore_pdpa",
                name="Personal Data Protection Act (Singapore)",
                short_name="PDPA (SG)",
                scope="Applies to all private-sector organisations collecting, using or disclosing personal data of individuals in Singapore.",
                framework="PDPA (SG)",
                text_resource="singapore/pdpa.txt",
            ),
        ],
    ),
]


def get_country(code: str) -> Optional[Country]:
    return next((c for c in CATALOG if c.code == code), None)


def get_regulation(regulation_id: str) -> Optional[tuple[Country, Regulation]]:
    for country in CATALOG:
        for reg in country.regulations:
            if reg.id == regulation_id:
                return country, reg
    return None
