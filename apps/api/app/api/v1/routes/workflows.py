from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.app.dependencies.auth import require_permission
from core.security.rbac import Permission, Principal
from workflows.engine.core import WorkflowDescriptor
from workflows.registry import workflow_descriptors

router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowListResponse(BaseModel):
    items: list[WorkflowDescriptor]
    total: int


@router.get("", response_model=WorkflowListResponse, summary="List workflow definitions")
async def list_workflows(
    _: Principal = Depends(require_permission(Permission.WORKFLOWS_READ)),
) -> WorkflowListResponse:
    items = workflow_descriptors()
    return WorkflowListResponse(items=items, total=len(items))
