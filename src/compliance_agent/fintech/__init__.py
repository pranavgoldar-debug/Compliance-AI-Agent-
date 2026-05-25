"""Fintech / remittance compliance calendar.

Per-country catalogues of recurring and event-based filings a remittance
fintech (Authorized Payment Service Provider) typically owes — covering
licensing, AML/CFT, forex/cross-border, direct/indirect tax, corporate,
labor, data protection, cybersecurity and consumer protection.

Each entry is curated to be reasonably accurate at the time of writing,
but rules change frequently — treat as a starting checklist, confirm with
counsel before relying on any specific due date.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class FintechFiling(BaseModel):
    s_no: int
    category: str = Field(description="High-level grouping: 'Licensing', 'AML / CFT', 'Direct Tax', etc.")
    area: str = Field(description="Sub-area within the category.")
    form_name: str = Field(description="Form, report, or filing name (e.g. 'GSTR-3B', 'STR', 'AOC-4').")
    authority: str = Field(description="Regulator or filing body (e.g. 'RBI', 'FinCEN', 'MAS').")
    frequency: str = Field(description="'Monthly', 'Quarterly', 'Annual', 'Half-Yearly', 'Event-based', 'One-time', etc.")
    due_date_rule: str = Field(description="Calendar rule that determines the due date for a CY (Jan-Dec) company.")
    payment_due: Optional[str] = Field(
        default=None,
        description="Payment deadline if distinct from the filing deadline.",
    )
    applicability: str = Field(description="'Mandatory', 'Conditional', 'Sector-specific', etc.")
    applicability_note: Optional[str] = Field(
        default=None,
        description="Short note on when this applies / does not apply to a remittance fintech.",
    )


class CountryFilings(BaseModel):
    country_code: str
    country_name: str
    flag: str
    filings: list[FintechFiling]


def _renumber(filings: list[FintechFiling]) -> list[FintechFiling]:
    """Stamp sequential s_no starting at 1."""
    return [f.model_copy(update={"s_no": i + 1}) for i, f in enumerate(filings)]


def _build_catalog() -> dict[str, CountryFilings]:
    from compliance_agent.fintech import (
        canada as _ca,
        eu as _eu,
        india as _india,
        lithuania as _lt,
        singapore as _sg,
        uae as _uae,
        uk as _uk,
        us as _us,
    )

    sources = [
        ("india", "India", "🇮🇳", _india.FILINGS),
        ("eu", "European Union", "🇪🇺", _eu.FILINGS),
        ("us", "United States", "🇺🇸", _us.FILINGS),
        ("uk", "United Kingdom", "🇬🇧", _uk.FILINGS),
        ("canada", "Canada", "🇨🇦", _ca.FILINGS),
        ("lithuania", "Lithuania", "🇱🇹", _lt.FILINGS),
        ("uae", "United Arab Emirates", "🇦🇪", _uae.FILINGS),
        ("singapore", "Singapore", "🇸🇬", _sg.FILINGS),
    ]
    return {
        code: CountryFilings(
            country_code=code,
            country_name=name,
            flag=flag,
            filings=_renumber(filings),
        )
        for code, name, flag, filings in sources
    }


CATALOG: dict[str, CountryFilings] = _build_catalog()


def get_country_filings(code: str) -> CountryFilings | None:
    return CATALOG.get(code)


def list_country_summaries() -> list[dict]:
    """Lightweight list for menu rendering — code, name, flag, count."""
    return [
        {
            "code": cf.country_code,
            "name": cf.country_name,
            "flag": cf.flag,
            "filing_count": len(cf.filings),
        }
        for cf in CATALOG.values()
    ]
