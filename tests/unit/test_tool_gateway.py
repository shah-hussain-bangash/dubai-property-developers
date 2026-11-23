from __future__ import annotations

from typing import Any, ClassVar

import pytest

from core.exceptions.errors import (
    AuthorizationError,
    ConflictError,
    PolicyViolationError,
    ToolPermissionError,
)
from core.policies.actions import ActionCategory, ApprovalPolicy
from core.policies.approvals import ApprovalStatus
from core.security.rbac import (
    SYSTEM_PRINCIPAL,
    Permission,
    Principal,
    Role,
)
from integrations.meta.client import MockWhatsAppClient
from tools.base import (
    BaseTool,
    ToolCallContext,
    ToolGateway,
    ToolRegistry,
    ToolResultStatus,
    ToolSpec,
)
from tools.whatsapp.tools import WhatsAppSendTool


class CountingSendTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="test.send",
        description="test outbound",
        category=ActionCategory.OUTBOUND_MESSAGE,
        permission=Permission.MESSAGES_SEND,
    )

    def __init__(self) -> None:
        self.calls = 0

    async def execute(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls += 1
        return {"sent": payload["to"]}


def _gateway(
    policy: ApprovalPolicy | None = None,
) -> tuple[ToolGateway, CountingSendTool]:
    registry = ToolRegistry()
    tool = CountingSendTool()

    registry.register(tool)
    registry.register(WhatsAppSendTool(MockWhatsAppClient()))

    return ToolGateway(
        registry,
        approval_policy=policy,
    ), tool


def _ctx(
    principal: Principal = SYSTEM_PRINCIPAL,
    allowed: set[str] | None = None,
) -> ToolCallContext:
    return ToolCallContext(
        principal=principal,
        tenant_id="demo-org",
        correlation_id="c-1",
        agent_id="tester",
        allowed_tools=frozenset(
            allowed if allowed is not None else {"test.send", "whatsapp.send_message"}
        ),
    )


async def test_allowlist_is_enforced_and_audited() -> None:
    gateway, _ = _gateway()

    with pytest.raises(ToolPermissionError):
        await gateway.invoke(
            _ctx(allowed=set()),
            "test.send",
            {"to": "x"},
        )

    assert gateway.audit.events[-1].outcome == "denied"


async def test_outbound_requires_approval_then_executes_as_approver() -> None:
    gateway, tool = _gateway()

    # The system agent can request approval without
    # having the permission to execute the outbound action.
    first = await gateway.invoke(
        _ctx(),
        "test.send",
        {"to": "x"},
    )

    assert first.status == ToolResultStatus.PENDING_APPROVAL
    assert tool.calls == 0
    assert first.approval_id is not None

    # Repeated requests must not generate duplicate approvals.
    again = await gateway.invoke(
        _ctx(),
        "test.send",
        {"to": "x"},
    )

    assert again.status == ToolResultStatus.PENDING_APPROVAL
    assert again.approval_id == first.approval_id
    assert tool.calls == 0

    # A sales manager can approve and execute the action.
    approver = Principal(
        subject="mgr",
        tenant_id="demo-org",
        roles=frozenset({Role.SALES_MANAGER}),
    )

    await gateway.approvals.decide(
        first.approval_id,
        approved=True,
        decided_by="mgr",
    )

    executed = await gateway.execute_approved(
        first.approval_id,
        approver,
    )

    assert executed.status == ToolResultStatus.EXECUTED
    assert executed.data == {"sent": "x"}
    assert tool.calls == 1

    # SECURITY REGRESSION:
    # The system agent still lacks MESSAGES_SEND permission.
    # Approval does not grant it permission to read the
    # cached execution result.
    with pytest.raises(AuthorizationError):
        await gateway.invoke(
            _ctx(),
            "test.send",
            {"to": "x"},
        )

    # Unauthorized replay must not execute the action again.
    assert tool.calls == 1
    assert gateway.audit.events[-1].outcome == "denied"

    # An authorized principal can access the cached result
    # without repeating the external action.
    replay = await gateway.invoke(
        _ctx(principal=approver),
        "test.send",
        {"to": "x"},
    )

    assert replay.status == ToolResultStatus.REPLAYED
    assert replay.data == {"sent": "x"}
    assert tool.calls == 1


async def test_rejected_approval_cannot_execute() -> None:
    gateway, tool = _gateway()

    pending = await gateway.invoke(
        _ctx(),
        "test.send",
        {"to": "y"},
    )

    assert pending.status == ToolResultStatus.PENDING_APPROVAL
    assert pending.approval_id is not None

    decided = await gateway.approvals.decide(
        pending.approval_id,
        approved=False,
        decided_by="mgr",
    )

    assert decided.status == ApprovalStatus.REJECTED

    with pytest.raises(ConflictError):
        await gateway.execute_approved(
            pending.approval_id,
            SYSTEM_PRINCIPAL,
        )

    assert tool.calls == 0


async def test_rbac_applies_when_approval_disabled() -> None:
    gateway, tool = _gateway(ApprovalPolicy(outbound_messages=False))

    # SYSTEM does not have MESSAGES_SEND permission.
    with pytest.raises(AuthorizationError):
        await gateway.invoke(
            _ctx(),
            "test.send",
            {"to": "x"},
        )

    assert tool.calls == 0
    assert gateway.audit.events[-1].outcome == "denied"


async def test_whatsapp_policy_blocks_before_approval() -> None:
    gateway, _ = _gateway()

    # WhatsApp consent is required.
    with pytest.raises(PolicyViolationError):
        await gateway.invoke(
            _ctx(),
            "whatsapp.send_message",
            {
                "to_e164": "+971500000001",
                "consent_whatsapp": False,
                "text": "hi",
            },
        )

    # Free-text messages outside the permitted
    # customer service window must be rejected.
    with pytest.raises(PolicyViolationError):
        await gateway.invoke(
            _ctx(),
            "whatsapp.send_message",
            {
                "to_e164": "+971500000001",
                "consent_whatsapp": True,
                "text": "hi",
                "last_inbound_at": None,
            },
        )

    assert await gateway.approvals.list_pending("demo-org") == []


async def test_editing_approval_snapshot_cannot_bypass_decision_or_change_payload() -> None:
    gateway, tool = _gateway()
    pending = await gateway.invoke(_ctx(), "test.send", {"to": "original"})
    assert pending.approval_id is not None
    snapshot = await gateway.approvals.get(pending.approval_id)
    snapshot.status = ApprovalStatus.APPROVED
    snapshot.payload["to"] = "tampered"
    manager = Principal(
        subject="manager", tenant_id="demo-org", roles=frozenset({Role.SALES_MANAGER})
    )
    with pytest.raises(ConflictError):
        await gateway.execute_approved(pending.approval_id, manager)
    assert tool.calls == 0
    await gateway.approvals.decide(pending.approval_id, approved=True, decided_by="manager")
    executed = await gateway.execute_approved(pending.approval_id, manager)
    assert executed.data == {"sent": "original"}
    assert tool.calls == 1
