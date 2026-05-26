"""System info — small endpoint the UI polls to flip the mode badge."""
from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(prefix="/api/system", tags=["system"])


class SystemInfo(BaseModel):
    mode: str  # "live" or "mock"
    ai_available: bool
    version: str


@router.get("/info", response_model=SystemInfo)
def system_info() -> SystemInfo:
    live = os.environ.get("COMPLIANCE_AGENT_LIVE") == "1"
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return SystemInfo(
        mode="live" if live and has_key else "mock",
        ai_available=live and has_key,
        version="0.6.0",
    )
