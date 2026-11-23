"""Tool invocation cannot use another tenant's permissions or cached results."""

from typing import Any, ClassVar
from unittest.mock import AsyncMock

import pytest

from agents.base.context import ExecutionContext
from core.exceptions.errors import AuthorizationError
from core.policies.actions import ActionCategory, ApprovalPolicy
from core.security.rbac import SYSTEM_PRINCIPAL, Permission, Principal, Role
from tools.base import (
    BaseTool,
    ToolCallContext,
    ToolGateway,
    ToolRegistry,
    ToolResultStatus,
    ToolSpec,
)


class TenantFixtureTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="test.tenant_scope",
        description="Fictional tenant-scope fixture with no external integration",
        category=ActionCategory.CRM_WRITE,
        permission=Permission.CRM_WRITE,
    )

    def __init__(self):
        self.validations = 0
        self.calls = 0

    def validate(self, payload):
        self.validations += 1

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return {"fixture": "result"}


def fixture_gateway(*, approval_required=False):
    registry = ToolRegistry()
    tool = TenantFixtureTool()
    registry.register(tool)
    gateway = ToolGateway(registry, approval_policy=ApprovalPolicy(crm_writes=approval_required))
    return gateway, tool


def fixture_context(actor_tenant, target_tenant):
    return ToolCallContext(
        principal=Principal(
            subject="fixture-manager",
            tenant_id=actor_tenant,
            roles=frozenset({Role.SALES_MANAGER}),
        ),
        tenant_id=target_tenant,
        correlation_id="fixture-tenant-scope",
        agent_id="fixture-agent",
        allowed_tools=frozenset({TenantFixtureTool.spec.name}),
    )


async def test_mismatched_tenant_is_denied_before_validation_or_cache_access(monkeypatch):
    gateway, tool = fixture_gateway()
    get = AsyncMock(return_value=None)
    monkeypatch.setattr(gateway.idempotency, "get", get)
    with pytest.raises(AuthorizationError, match="different organization"):
        await gateway.invoke(fixture_context("tenant-a", "tenant-b"), tool.spec.name, {})
    assert tool.validations == tool.calls == 0
    get.assert_not_awaited()
    assert gateway.audit.events[-1].outcome == "denied"


async def test_mismatched_tenant_cannot_replay_another_tenants_cached_result():
    gateway, tool = fixture_gateway()
    first = await gateway.invoke(fixture_context("tenant-b", "tenant-b"), tool.spec.name, {})
    assert first.status == ToolResultStatus.EXECUTED
    with pytest.raises(AuthorizationError):
        await gateway.invoke(fixture_context("tenant-a", "tenant-b"), tool.spec.name, {})
    assert tool.calls == 1
    assert gateway.audit.events[-1].outcome == "denied"


async def test_mismatched_tenant_cannot_create_an_approval():
    gateway, tool = fixture_gateway(approval_required=True)
    with pytest.raises(AuthorizationError):
        await gateway.invoke(fixture_context("tenant-a", "tenant-b"), tool.spec.name, {})
    assert await gateway.approvals.list_pending("tenant-b") == []
    assert tool.validations == tool.calls == 0


async def test_matching_tenant_keeps_normal_execution():
    gateway, tool = fixture_gateway()
    result = await gateway.invoke(fixture_context("tenant-a", "tenant-a"), tool.spec.name, {})
    assert result.status == ToolResultStatus.EXECUTED
    assert result.data == {"fixture": "result"}
    assert tool.validations > 0
    assert tool.calls == 1


def test_explicit_system_context_uses_a_tenant_scoped_identity():
    original_tenant = SYSTEM_PRINCIPAL.tenant_id
    context = ExecutionContext.system("tenant-b", "fixture-system-scope")
    assert context.principal.tenant_id == context.tenant_id == "tenant-b"
    assert context.principal.roles == SYSTEM_PRINCIPAL.roles
    assert context.principal.has(Permission.CRM_WRITE)
    assert not context.principal.has(Permission.MESSAGES_SEND)
    assert context.correlation_id == "fixture-system-scope"
    assert SYSTEM_PRINCIPAL.tenant_id == original_tenant


def test_default_system_context_keeps_its_existing_identity_values():
    context = ExecutionContext.system()
    assert context.principal == SYSTEM_PRINCIPAL
    assert context.tenant_id == SYSTEM_PRINCIPAL.tenant_id


async def test_scoped_system_context_can_still_execute_allowed_tools():
    gateway, tool = fixture_gateway()
    context = ExecutionContext.system("tenant-b")
    tool_context = ToolCallContext(
        principal=context.principal,
        tenant_id=context.tenant_id,
        correlation_id=context.correlation_id,
        agent_id="fixture-agent",
        allowed_tools=frozenset({tool.spec.name}),
    )
    result = await gateway.invoke(tool_context, tool.spec.name, {})
    assert result.status == ToolResultStatus.EXECUTED
    assert tool.calls == 1
