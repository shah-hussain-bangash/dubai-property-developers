"""Mutating tool responses cannot change later idempotent replays."""

from typing import Any, ClassVar

import pytest

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


class SnapshotFixtureTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="test.snapshot_send",
        description="Fictional result snapshot fixture with no external integration",
        category=ActionCategory.OUTBOUND_MESSAGE,
        permission=Permission.MESSAGES_SEND,
    )

    def __init__(self):
        self.calls = 0

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return {"receipt": {"items": [{"id": "fixture-item"}]}}


@pytest.mark.parametrize("mutated_response", ["executed", "replayed"])
async def test_gateway_replay_keeps_original_nested_receipt(mutated_response):
    registry = ToolRegistry()
    tool = SnapshotFixtureTool()
    registry.register(tool)
    gateway = ToolGateway(registry, approval_policy=ApprovalPolicy(outbound_messages=False))
    ctx = ToolCallContext(
        principal=Principal(
            subject="fixture-manager", tenant_id="demo-org", roles=frozenset({Role.SALES_MANAGER})
        ),
        tenant_id="demo-org",
        correlation_id="fixture-snapshot-123",
        agent_id="fixture-agent",
        allowed_tools=frozenset({tool.spec.name}),
    )
    payload = {"to": "fixture-recipient"}
    executed = await gateway.invoke(ctx, tool.spec.name, payload)
    assert executed.status == ToolResultStatus.EXECUTED
    target = executed
    if mutated_response == "replayed":
        target = await gateway.invoke(ctx, tool.spec.name, payload)
        assert target.status == ToolResultStatus.REPLAYED
    target.data["receipt"]["items"][0]["id"] = "changed-by-caller"
    replay = await gateway.invoke(ctx, tool.spec.name, payload)
    assert replay.status == ToolResultStatus.REPLAYED
    assert replay.data == {"receipt": {"items": [{"id": "fixture-item"}]}}
    assert tool.calls == 1
