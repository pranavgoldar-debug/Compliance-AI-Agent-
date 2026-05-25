"""API routers for the Aspora Compliance OS surface."""
from compliance_agent.api.dashboard import router as dashboard_router
from compliance_agent.api.entities import router as entities_router
from compliance_agent.api.obligations import (
    calendar_router,
    router as obligations_router,
)
from compliance_agent.api.rules import router as rules_router
from compliance_agent.api.tasks import router as tasks_router

__all__ = [
    "dashboard_router",
    "entities_router",
    "obligations_router",
    "calendar_router",
    "rules_router",
    "tasks_router",
]
