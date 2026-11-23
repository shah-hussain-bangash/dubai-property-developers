"""Agent allowlists stay fixed throughout a tool-call context's lifetime."""

from typing import Any, ClassVar

import pytest

from core.exceptions.errors import ToolPermissionError
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


class AllowlistFixtureTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="test.allowlist_snapshot",
        description="Fictional allowlist fixture with no external integration",
        category=ActionCategory.CRM_WRITE,
        permission=Permission.CRM_WRITE,
    )

    def __init__(self):
        self.calls = 0

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return {"fixture": "result"}


def fixture_gateway():
    tool = AllowlistFixtureTool()
    registry = ToolRegistry()
    registry.register(tool)
    return ToolGateway(registry, approval_policy=ApprovalPolicy(crm_writes=False)), tool


def fixture_context(allowed_tools):
    return ToolCallContext(
        principal=Principal(
            subject="fixture-manager",
            tenant_id="fixture",
            roles=frozenset({Role.SALES_MANAGER}),
        ),
        tenant_id="fixture",
        correlation_id="fixture-allowlist-snapshot",
        agent_id="fixture-agent",
        allowed_tools=allowed_tools,
    )


async def test_adding_to_input_allowlist_does_not_authorize_existing_context():
    gateway, tool = fixture_gateway()
    allowed_tools = set()
    context = fixture_context(allowed_tools)
    allowed_tools.add(tool.spec.name)

    with pytest.raises(ToolPermissionError):
        await gateway.invoke(context, tool.spec.name, {})
    assert tool.calls == 0
    assert gateway.audit.events[-1].outcome == "denied"
    assert isinstance(context.allowed_tools, frozenset)


async def test_clearing_input_allowlist_keeps_original_authorization():
    gateway, tool = fixture_gateway()
    allowed_tools = {tool.spec.name}
    context = fixture_context(allowed_tools)
    allowed_tools.clear()

    result = await gateway.invoke(context, tool.spec.name, {})
    assert result.status == ToolResultStatus.EXECUTED
    assert tool.calls == 1


async def test_new_context_can_use_explicitly_expanded_allowlist():
    gateway, tool = fixture_gateway()
    allowed_tools = set()
    fixture_context(allowed_tools)
    allowed_tools.add(tool.spec.name)

    result = await gateway.invoke(fixture_context(allowed_tools), tool.spec.name, {})
    assert result.status == ToolResultStatus.EXECUTED
    assert tool.calls == 1
