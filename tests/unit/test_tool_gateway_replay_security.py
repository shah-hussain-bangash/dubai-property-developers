from __future__ import annotations

from typing import Any, ClassVar

import pytest

from core.exceptions.errors import AuthorizationError
from core.policies.actions import ActionCategory, ApprovalPolicy
from core.security.rbac import Permission, Principal, Role
from tools.base import (
    BaseTool,
    ToolCallContext,
    ToolGateway,
    ToolRegistry,
    ToolResultStatus,
    ToolSpec,
)


class CountingCRMTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="test.secure_crm_write",
        description="Test secure CRM action",
        category=ActionCategory.CRM_WRITE,
        permission=Permission.CRM_WRITE,
    )

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return {"external_id": "mock-lead-001"}


def context(principal: Principal) -> ToolCallContext:
    return ToolCallContext(
        principal=principal,
        tenant_id="demo-org",
        correlation_id="security-replay-test",
        agent_id="crm",
        allowed_tools=frozenset({"test.secure_crm_write"}),
    )


@pytest.mark.asyncio
async def test_cached_replay_requires_current_rbac_permission() -> None:
    registry = ToolRegistry()
    tool = CountingCRMTool()
    registry.register(tool)

    gateway = ToolGateway(
        registry,
        approval_policy=ApprovalPolicy(crm_writes=False),
    )

    authorized = Principal(
        subject="authorized-user",
        tenant_id="demo-org",
        roles=frozenset({Role.ADMIN}),
    )

    unauthorized = Principal(
        subject="unauthorized-user",
        tenant_id="demo-org",
        roles=frozenset(),
    )

    payload = {"local_lead_id": "lead-001"}

    first = await gateway.invoke(
        context(authorized),
        "test.secure_crm_write",
        payload,
    )

    assert first.status == ToolResultStatus.EXECUTED
    assert tool.calls == 1

    with pytest.raises(AuthorizationError):
        await gateway.invoke(
            context(unauthorized),
            "test.secure_crm_write",
            payload,
        )

    assert tool.calls == 1
    assert gateway.audit.events[-1].outcome == "denied"
