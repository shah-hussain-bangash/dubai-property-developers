"""One tool invocation keeps one payload across validation, approval, and execution."""

from collections.abc import Callable
from copy import deepcopy
from typing import Any, ClassVar

from core.policies.actions import ActionCategory, ApprovalPolicy
from core.resilience.idempotency import make_idempotency_key
from core.security.rbac import Permission, Principal, Role
from tools.base import (
    BaseTool,
    ToolCallContext,
    ToolGateway,
    ToolRegistry,
    ToolResultStatus,
    ToolSpec,
)


class PayloadFixtureTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="test.payload_snapshot",
        description="Fictional payload fixture with no external integration",
        category=ActionCategory.OUTBOUND_MESSAGE,
        permission=Permission.MESSAGES_SEND,
    )

    def __init__(self):
        self.calls = 0
        self.on_execute: Callable[[], None] | None = None
        self.normalize = False

    def validate(self, payload):
        if self.normalize:
            payload["details"]["validated"] = True

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        if self.on_execute is not None:
            self.on_execute()
        return deepcopy(payload)


def fixture_gateway(*, approval_required=False):
    registry = ToolRegistry()
    tool = PayloadFixtureTool()
    registry.register(tool)
    gateway = ToolGateway(
        registry, approval_policy=ApprovalPolicy(outbound_messages=approval_required)
    )
    ctx = ToolCallContext(
        principal=Principal(
            subject="fixture-manager", tenant_id="tenant-a", roles=frozenset({Role.SALES_MANAGER})
        ),
        tenant_id="tenant-a",
        correlation_id="fixture-payload-snapshot",
        agent_id="fixture-agent",
        allowed_tools=frozenset({tool.spec.name}),
    )
    return gateway, tool, ctx


def fixture_payload():
    return {"details": {"items": ["original"]}}


async def test_cache_lookup_edits_cannot_change_execution_or_its_replay(monkeypatch):
    gateway, tool, ctx = fixture_gateway()
    payload = fixture_payload()
    original_get = gateway.idempotency.get

    async def get(key):
        payload["details"]["items"][0] = "changed"
        return await original_get(key)

    monkeypatch.setattr(gateway.idempotency, "get", get)
    executed = await gateway.invoke(ctx, tool.spec.name, payload)
    assert executed.data == fixture_payload()
    assert executed.idempotency_key == make_idempotency_key(
        tool.spec.name, fixture_payload(), scope=ctx.tenant_id
    )
    replay = await gateway.invoke(ctx, tool.spec.name, fixture_payload())
    assert replay.status == ToolResultStatus.REPLAYED
    assert replay.data == fixture_payload()
    assert tool.calls == 1


async def test_approval_lookup_edits_cannot_change_the_requested_payload(monkeypatch):
    gateway, tool, ctx = fixture_gateway(approval_required=True)
    payload = fixture_payload()
    original_find = gateway.approvals.find_by_idempotency_key

    async def find(key):
        payload["details"]["items"][0] = "changed"
        return await original_find(key)

    monkeypatch.setattr(gateway.approvals, "find_by_idempotency_key", find)
    pending = await gateway.invoke(ctx, tool.spec.name, payload)
    assert pending.status == ToolResultStatus.PENDING_APPROVAL
    assert pending.approval_id is not None
    request = await gateway.approvals.get(pending.approval_id)
    assert request.payload == fixture_payload()
    assert request.idempotency_key == make_idempotency_key(
        tool.spec.name, fixture_payload(), scope=ctx.tenant_id
    )
    assert tool.calls == 0


async def test_caller_edits_during_tool_execution_do_not_change_its_input():
    gateway, tool, ctx = fixture_gateway()
    payload = fixture_payload()

    def change_caller_payload():
        payload["details"]["items"][0] = "changed"

    tool.on_execute = change_caller_payload
    result = await gateway.invoke(ctx, tool.spec.name, payload)
    assert payload["details"]["items"] == ["changed"]
    assert result.data == fixture_payload()


async def test_validation_can_normalize_the_snapshot_without_mutating_the_caller():
    gateway, tool, ctx = fixture_gateway()
    tool.normalize = True
    payload = fixture_payload()
    result = await gateway.invoke(ctx, tool.spec.name, payload)
    assert payload == fixture_payload()
    expected = fixture_payload()
    expected["details"]["validated"] = True
    assert result.data == expected
    assert result.idempotency_key == make_idempotency_key(
        tool.spec.name, expected, scope=ctx.tenant_id
    )


async def test_explicit_later_invocation_uses_updated_payload_and_a_new_key():
    gateway, tool, ctx = fixture_gateway()
    payload = fixture_payload()
    first = await gateway.invoke(ctx, tool.spec.name, payload)
    payload["details"]["items"][0] = "updated"
    second = await gateway.invoke(ctx, tool.spec.name, payload)
    assert first.data == fixture_payload()
    assert second.data == payload
    assert second.idempotency_key != first.idempotency_key
    assert first.status == second.status == ToolResultStatus.EXECUTED
    assert tool.calls == 2
