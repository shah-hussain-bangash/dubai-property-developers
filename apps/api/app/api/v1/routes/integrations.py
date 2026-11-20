from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api.app.dependencies.auth import require_permission
from apps.api.app.dependencies.runtime import get_runtime
from core.security.rbac import Permission, Principal
from schemas.integrations.models import IntegrationDescriptor
from workflows.runtime import PlatformRuntime

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationDescriptor], summary="Integration modes and status")
async def list_integrations(
    runtime: PlatformRuntime = Depends(get_runtime),
    _: Principal = Depends(require_permission(Permission.SETTINGS_ADMIN)),
) -> list[IntegrationDescriptor]:
    return runtime.integrations.descriptors
