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
