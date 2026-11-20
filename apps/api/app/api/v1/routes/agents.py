from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api.app.dependencies.auth import require_permission
from apps.api.app.dependencies.runtime import get_runtime
from core.security.rbac import Permission, Principal
from schemas.agents.models import AgentListResponse
from workflows.runtime import PlatformRuntime

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=AgentListResponse, summary="List registered AI agents")
async def list_agents(
    runtime: PlatformRuntime = Depends(get_runtime),
    _: Principal = Depends(require_permission(Permission.AGENTS_READ)),
) -> AgentListResponse:
    items = runtime.agents.descriptors()
    return AgentListResponse(items=items, total=len(items))
