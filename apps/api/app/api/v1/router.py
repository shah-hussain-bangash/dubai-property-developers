from __future__ import annotations

from fastapi import APIRouter

from apps.api.app.api.v1.routes import (
    agents,
    approvals,
    conversation_demo,
    integrations,
    knowledge_demo,
    local_ai,
    local_ai_knowledge,
    local_ai_properties,
    leads,
    property_demo,
    prospect_research,
    workflow_demo,
    workflows,
)
from core.config.settings import Settings


def build_v1_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(agents.router)
    router.include_router(workflows.router)
    router.include_router(approvals.router)
    router.include_router(integrations.router)
    if settings.enable_dev_routes and settings.is_dev_like:
        if settings.prospect_storage_enabled:
            router.include_router(prospect_research.router)
        if settings.local_ai_enabled:
            router.include_router(local_ai.router)
            router.include_router(local_ai_knowledge.router)
            router.include_router(local_ai_properties.router)
        router.include_router(leads.router)
        router.include_router(property_demo.router)
        router.include_router(knowledge_demo.router)
        router.include_router(conversation_demo.router)
        router.include_router(workflow_demo.router)
    return router
