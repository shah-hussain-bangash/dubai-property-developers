from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import pytest

from core.policies.actions import ActionCategory
from core.security.rbac import Permission, Principal, Role
from tools.base import (
    BaseTool,
    ToolCallContext,
    ToolGateway,
    ToolRegistry,
    ToolResultStatus,
    ToolSpec,
)


class ConcurrentApprovedTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="test.concurrent_approved_send",
        description="Test concurrent approved execution",
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
        self.started.set()
        await self.release.wait()
        return {"message_id": f"message-{self.calls}"}


@pytest.mark.asyncio
async def test_concurrent_approved_action_executes_only_once() -> None:
    registry = ToolRegistry()
    tool = ConcurrentApprovedTool()
    registry.register(tool)

    gateway = ToolGateway(registry)

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
        correlation_id="concurrent-approval-test",
        agent_id="test-agent",
        allowed_tools=frozenset({"test.concurrent_approved_send"}),
    )

    pending = await gateway.invoke(
        ctx,
        "test.concurrent_approved_send",
        {"to": "mock-recipient"},
    )

    assert pending.status == ToolResultStatus.PENDING_APPROVAL
    assert pending.approval_id is not None

    await gateway.approvals.decide(
        pending.approval_id,
        approved=True,
        decided_by="manager",
    )

    first_task = asyncio.create_task(gateway.execute_approved(pending.approval_id, approver))

    second_task = None

    try:
        await asyncio.wait_for(tool.started.wait(), timeout=2)

        second_task = asyncio.create_task(gateway.execute_approved(pending.approval_id, approver))

        # Allow the second invocation to reach execution or wait.
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
