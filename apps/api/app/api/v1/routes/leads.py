"""DEVELOPMENT-ONLY lead demo endpoint.

Runs the Lead Processing workflow against mock integrations and fictional data.
Mounted only when ENABLE_DEV_ROUTES=true (refused outside development/test).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agents.base.context import ExecutionContext
from apps.api.app.dependencies.auth import require_permission
from apps.api.app.dependencies.runtime import get_runtime
from core.observability.context import get_correlation_id, new_correlation_id
from core.security.rbac import Permission, Principal
from schemas.leads.models import LeadSubmission
from workflows.engine.core import StepRecord, WorkflowStatus
from workflows.lead_flow import LEAD_PROCESSING, LeadFlowState
from workflows.runtime import PlatformRuntime

router = APIRouter(prefix="/leads", tags=["development-only"])


def _require_isolated_demo(runtime: PlatformRuntime) -> None:
    settings = runtime.settings
    if not (
        settings.is_dev_like
        and settings.auth_mode == "dev"
        and settings.enable_dev_routes
        and settings.integrations_mode == "mock"
        and settings.llm_provider == "mock"
        and settings.lead_store_backend == "memory"
        and settings.workflow_store_backend == "memory"
    ):
        raise HTTPException(status_code=404, detail="Isolated demo processing is unavailable")


@router.get("/demo-capabilities", summary="[DEV ONLY] Isolated demo availability")
async def demo_capabilities(
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.WORKFLOWS_EXECUTE)),
) -> dict[str, bool]:
    _require_isolated_demo(runtime)
    return {"enabled": True, "mock_integrations": True, "memory_storage": True}


class LeadDemoResponse(BaseModel):
    dev_only: bool = True
    uses_mock_integrations: bool = True
    execution_id: str
    status: WorkflowStatus
    steps: list[StepRecord]
    result: dict[str, Any]
    error: dict[str, Any] | None = None


@router.post(
    "/demo-process",
    response_model=LeadDemoResponse,
    summary="[DEV ONLY] Run the lead processing workflow with mock integrations",
    description="Development-only. Uses mock CRM and fictional data; never connects to live systems.",
)
async def demo_process(
    submission: LeadSubmission,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.WORKFLOWS_EXECUTE)),
) -> LeadDemoResponse:
    _require_isolated_demo(runtime)
    ctx = ExecutionContext(
        principal=principal,
        tenant_id=principal.tenant_id,
        correlation_id=get_correlation_id() or new_correlation_id(),
    )
    run, state = await runtime.runner.run(
        LEAD_PROCESSING, LeadFlowState(submission=submission), ctx
    )
    return LeadDemoResponse(
        execution_id=run.execution_id,
        status=run.status,
        steps=run.steps,
        result=state.model_dump(mode="json", exclude={"submission"}),
        error=run.error,
    )
