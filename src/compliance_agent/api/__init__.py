"""API routers for the Aspora Compliance OS surface."""
from compliance_agent.api.chat import router as chat_router
from compliance_agent.api.dashboard import router as dashboard_router
from compliance_agent.api.entities import router as entities_router
from compliance_agent.api.obligations import (
    calendar_router,
    router as obligations_router,
)
from compliance_agent.api.rules import router as rules_router
from compliance_agent.api.rules_ai import router as rules_ai_router
from compliance_agent.api.tasks import router as tasks_router

__all__ = [
    "chat_router",
    "dashboard_router",
    "entities_router",
    "obligations_router",
    "calendar_router",
    "rules_router",
    "rules_ai_router",
    "tasks_router",
]
