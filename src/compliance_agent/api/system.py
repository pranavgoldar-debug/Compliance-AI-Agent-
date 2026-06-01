"""System info — small endpoint the UI polls to flip the mode badge."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from compliance_agent.ai.llm_client import active_backend, ai_available


router = APIRouter(prefix="/api/system", tags=["system"])


class SystemInfo(BaseModel):
    mode: str  # "live" or "mock"
    ai_available: bool
    backend: str  # "anthropic" / "openrouter" / "mock"
    version: str


@router.get("/info", response_model=SystemInfo)
def system_info() -> SystemInfo:
    available = ai_available()
    return SystemInfo(
        mode="live" if available else "mock",
        ai_available=available,
        backend=active_backend(),
        version="0.6.0",
    )
