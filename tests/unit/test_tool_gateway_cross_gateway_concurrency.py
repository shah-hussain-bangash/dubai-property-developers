from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import pytest

from core.policies.actions import ActionCategory
from core.policies.approvals import InMemoryApprovalStore
from core.resilience.idempotency import InMemoryIdempotencyStore
from core.security.rbac import Permission, Principal, Role
from tools.base import (
    BaseTool,
    ToolCallContext,
    ToolGateway,
    ToolRegistry,
    ToolResultStatus,
    ToolSpec,
)


class SharedGatewayTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="test.cross_gateway_send",
        description="Test execution across gateway instances",
        category=ActionCategory.OUTBOUND_MESSAGE,
        permission=Permission.MESSAGES_SEND,
    )

    def __init__(self) -> None:
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls += 1
        call_number = self.calls
        self.started.set()
        await self.release.wait()

        return {
            "message_id": f"message-{call_number}",
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first_entrypoint", "second_entrypoint"),
    [
        ("approved", "approved"),
        ("approved", "invoke"),
        ("invoke", "approved"),
        ("invoke", "invoke"),
    ],
)
async def test_shared_gateways_must_not_execute_action_twice(
    first_entrypoint: str, second_entrypoint: str
) -> None:
    registry = ToolRegistry()
    tool = SharedGatewayTool()
    registry.register(tool)

    shared_approvals = InMemoryApprovalStore()
    shared_idempotency = InMemoryIdempotencyStore()

    gateway_a = ToolGateway(
        registry,
        approvals=shared_approvals,
        idempotency=shared_idempotency,
    )

    gateway_b = ToolGateway(
        registry,
        approvals=shared_approvals,
        idempotency=shared_idempotency,
    )

    requester = Principal(
        subject="system",
        tenant_id="demo-org",
        roles=frozenset({Role.SYSTEM}),
    )

    approver = Principal(
        subject="manager",
        tenant_id="demo-org",
        roles=frozenset({Role.SALES_MANAGER}),
    )

    ctx = ToolCallContext(
        principal=requester,
        tenant_id="demo-org",
        correlation_id="cross-gateway-test",
        agent_id="test-agent",
        allowed_tools=frozenset({"test.cross_gateway_send"}),
    )

    pending = await gateway_a.invoke(
        ctx,
        "test.cross_gateway_send",
        {"to": "mock-recipient"},
    )

    assert pending.status == ToolResultStatus.PENDING_APPROVAL
    assert pending.approval_id is not None

    await shared_approvals.decide(
        pending.approval_id,
        approved=True,
        decided_by="manager",
    )

    async def execute(gateway: ToolGateway, entrypoint: str):
        if entrypoint == "approved":
            return await gateway.execute_approved(pending.approval_id, approver)
        return await gateway.invoke(
            ToolCallContext(
                principal=approver,
                tenant_id="demo-org",
                correlation_id="cross-gateway-invoke-test",
            ),
            "test.cross_gateway_send",
            {"to": "mock-recipient"},
        )

    first_task = asyncio.create_task(execute(gateway_a, first_entrypoint))

    second_task = None

    try:
        await asyncio.wait_for(tool.started.wait(), timeout=2)

        second_task = asyncio.create_task(execute(gateway_b, second_entrypoint))

        await asyncio.sleep(0.05)

        tool.release.set()

        first, second = await asyncio.wait_for(
            asyncio.gather(first_task, second_task),
            timeout=2,
        )

        assert tool.calls == 1
        assert first.data == second.data
        assert {
            first.status,
            second.status,
        } == {
            ToolResultStatus.EXECUTED,
            ToolResultStatus.REPLAYED,
        }

    finally:
        tool.release.set()

        tasks = [task for task in (first_task, second_task) if task is not None]

        for task in tasks:
            if not task.done():
                task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
