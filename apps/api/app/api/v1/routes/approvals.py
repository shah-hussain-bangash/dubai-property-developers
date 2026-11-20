"""Human-in-the-loop approval endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from apps.api.app.dependencies.auth import require_permission
from apps.api.app.dependencies.runtime import get_runtime
from core.exceptions.errors import NotFoundError
from core.policies.approvals import ApprovalStatus
from core.security.rbac import Permission, Principal
from tools.base import ToolResult
from workflows.runtime import PlatformRuntime

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalView(BaseModel):
    approval_id: str
    tool_name: str
    action_category: str
    requested_by: str
    requested_by_agent: str | None
    reason: str
    status: ApprovalStatus
    payload_preview: dict[str, Any]


class DecisionRequest(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=1000)


class DecisionResponse(BaseModel):
    approval: ApprovalView
    execution: ToolResult | None = None


@router.get("/pending", response_model=list[ApprovalView])
async def list_pending(
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.APPROVALS_DECIDE)),
) -> list[ApprovalView]:
    pending = await runtime.approvals.list_pending(principal.tenant_id)
    return [_view(r) for r in pending]


@router.post("/{approval_id}/decision", response_model=DecisionResponse)
async def decide(
    approval_id: str,
    body: DecisionRequest,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.APPROVALS_DECIDE)),
) -> DecisionResponse:
    request = await runtime.approvals.get(approval_id)
    if request.tenant_id != principal.tenant_id:
        raise NotFoundError(f"approval {approval_id} not found")  # no cross-tenant disclosure
    decided = await runtime.approvals.decide(
        approval_id, approved=body.approve, decided_by=principal.subject, note=body.note
    )
    execution = None
    if body.approve:
        # Executes as the approving human; their own RBAC permissions still apply.
        execution = await runtime.gateway.execute_approved(approval_id, principal)
    return DecisionResponse(approval=_view(decided), execution=execution)


def _view(request: Any) -> ApprovalView:
    return ApprovalView(
        approval_id=request.approval_id,
        tool_name=request.tool_name,
        action_category=request.action_category,
        requested_by=request.requested_by,
        requested_by_agent=request.requested_by_agent,
        reason=request.reason,
        status=request.status,
        payload_preview=request.display_payload(),
    )
