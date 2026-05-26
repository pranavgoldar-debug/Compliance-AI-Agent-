"""API routers for the Aspora Compliance OS surface."""
from compliance_agent.api.activities import router as activities_router
from compliance_agent.api.ai_assist import router as ai_assist_router
from compliance_agent.api.chat import router as chat_router
from compliance_agent.api.dashboard import router as dashboard_router
from compliance_agent.api.documents import (
    entity_uploads as document_entity_upload_router,
    obligation_uploads as document_obligation_upload_router,
    router as documents_router,
)
from compliance_agent.api.entities import router as entities_router
from compliance_agent.api.exports import router as exports_router
from compliance_agent.api.integrations import (
    admin_router as integrations_admin_router,
    me_router as integrations_me_router,
)
from compliance_agent.api.notifications import router as notifications_router
from compliance_agent.api.obligations import (
    calendar_router,
    router as obligations_router,
)
from compliance_agent.api.retention import router as retention_router
from compliance_agent.api.rules import router as rules_router
from compliance_agent.api.rules_ai import router as rules_ai_router
from compliance_agent.api.rules_import import router as rules_import_router
from compliance_agent.api.system import router as system_router
from compliance_agent.api.tasks import router as tasks_router
from compliance_agent.api.users import router as users_router

__all__ = [
    "activities_router",
    "ai_assist_router",
    "chat_router",
    "dashboard_router",
    "documents_router",
    "document_entity_upload_router",
    "document_obligation_upload_router",
    "entities_router",
    "exports_router",
    "integrations_admin_router",
    "integrations_me_router",
    "notifications_router",
    "obligations_router",
    "calendar_router",
    "retention_router",
    "rules_router",
    "rules_ai_router",
    "rules_import_router",
    "system_router",
    "tasks_router",
    "users_router",
]
