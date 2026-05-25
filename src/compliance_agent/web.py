"""FastAPI app serving the country-picker UI and JSON endpoints.

Endpoints:
  GET /                             — single-page UI
  GET /api/countries                — list of countries + their regulations
  GET /api/regulations/{reg_id}     — extracted requirements (+ optional verification)

Default mode is mock (no API key needed). Set `COMPLIANCE_AGENT_LIVE=1` and
provide `ANTHROPIC_API_KEY` to switch to live Claude extraction.
"""
from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from compliance_agent.catalog import CATALOG, Country, Regulation, get_regulation
from compliance_agent.fintech import (
    CATALOG as FINTECH_CATALOG,
    CountryFilings,
    get_country_filings,
    list_country_summaries,
)
from compliance_agent.mock import mock_extract, mock_verify
from compliance_agent.models import ExtractionResult, VerificationResult


class CountrySummary(BaseModel):
    code: str
    name: str
    flag: str
    regulations: list[Regulation]


class RegulationView(BaseModel):
    country: str
    country_code: str
    flag: str
    regulation: Regulation
    extraction: ExtractionResult
    verification: Optional[VerificationResult] = None


def _is_live() -> bool:
    return os.environ.get("COMPLIANCE_AGENT_LIVE") == "1"


def create_app() -> FastAPI:
    app = FastAPI(title="Compliance AI Agent", version="0.2.0")

    static_dir = Path(str(files("compliance_agent.data").joinpath("static")))

    @app.get("/api/countries", response_model=list[CountrySummary])
    def list_countries() -> list[CountrySummary]:
        return [
            CountrySummary(code=c.code, name=c.name, flag=c.flag, regulations=c.regulations)
            for c in CATALOG
        ]

    @app.get("/api/regulations/{regulation_id}", response_model=RegulationView)
    def get_regulation_view(regulation_id: str, verify: bool = True) -> RegulationView:
        found = get_regulation(regulation_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"Unknown regulation: {regulation_id}")
        country, regulation = found

        try:
            source_text = regulation.read_text()
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Regulation text file missing on disk: {regulation.text_resource}",
            ) from exc

        if _is_live():
            from compliance_agent.extractor import ComplianceExtractor

            extraction = ComplianceExtractor().extract(source_text, framework_hint=regulation.framework)
        else:
            extraction = mock_extract(source_text, framework_hint=regulation.framework)

        verification: Optional[VerificationResult] = None
        if verify:
            if _is_live():
                from compliance_agent.verifier import ComplianceVerifier

                verification = ComplianceVerifier().verify(source_text, extraction)
            else:
                verification = mock_verify(source_text, extraction)

        return RegulationView(
            country=country.name,
            country_code=country.code,
            flag=country.flag,
            regulation=regulation,
            extraction=extraction,
            verification=verification,
        )

    @app.get("/api/fintech/countries")
    def list_fintech_countries() -> list[dict]:
        return list_country_summaries()

    @app.get("/api/fintech/{country_code}", response_model=CountryFilings)
    def get_fintech_filings(country_code: str) -> CountryFilings:
        cf = get_country_filings(country_code)
        if cf is None:
            raise HTTPException(status_code=404, detail=f"Unknown country: {country_code}")
        return cf

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app


app = create_app()
