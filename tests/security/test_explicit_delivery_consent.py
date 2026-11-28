"""Sending requires a boolean opt-in, including at the final delivery boundary."""

from datetime import UTC, datetime

import pytest

from core.exceptions.errors import PolicyViolationError
from integrations.meta.client import MockWhatsAppClient
from tools.base import ToolCallContext, ToolGateway, ToolRegistry
from tools.email.sender import MockEmailSender
from tools.email.tools import EmailSendTool
from tools.whatsapp.tools import WhatsAppSendTool

INVALID = [False, None, 1, "false", "true", {"approved": False}]


@pytest.mark.parametrize("consent", INVALID)
@pytest.mark.parametrize("channel", ["whatsapp", "email"])
@pytest.mark.parametrize("entry", ["gateway", "standalone"])
async def test_non_boolean_optin_cannot_reach_delivery(consent, channel, entry, manager):
    if channel == "whatsapp":
        client = MockWhatsAppClient()
        tool = WhatsAppSendTool(client)
        payload = {
            "to_e164": "+971500000001",
            "text": "Fictional portfolio reply",
            "last_inbound_at": datetime.now(UTC).isoformat(),
            "consent_whatsapp": consent,
        }
    else:
        client = MockEmailSender()
        tool = EmailSendTool(client)
        payload = {
            "to": "fixture@example.com",
            "subject": "Fictional portfolio message",
            "body": "Fictional portfolio reply",
            "is_marketing": True,
            "consent_marketing": consent,
        }
    registry = ToolRegistry()
    registry.register(tool)
    gateway = ToolGateway(registry)
    with pytest.raises(PolicyViolationError):
        if entry == "standalone":
            await tool.execute(payload)
        else:
            await gateway.invoke(
                ToolCallContext(manager, manager.tenant_id, "fictional-explicit-consent"),
                tool.spec.name,
                payload,
            )
    assert client.outbox == []
    assert await gateway.approvals.list_pending(manager.tenant_id) == []


@pytest.mark.parametrize("consent", INVALID)
async def test_queued_reply_rechecks_explicit_stored_consent(runtime, ctx, consent):
    agent = runtime.agents.get("whatsapp")
    conversation = "fictional-explicit-stored-consent"
    queued = await agent.run(
        {
            "conversation_id": conversation,
            "from_e164": "+971500000001",
            "text": "Tell me about the fictional gardens",
            "received_at": datetime.now(UTC).isoformat(),
            "draft_reply": "Fictional portfolio reply",
            "consent_whatsapp": True,
            "send_reply": True,
        },
        ctx,
    )
    assert queued.status == "pending_approval"
    await agent.conversation_memory(ctx).update_state(conversation, {"consent_whatsapp": consent})
    await runtime.approvals.decide(
        queued.output.approval_id, approved=True, decided_by=ctx.principal.subject
    )
    with pytest.raises(PolicyViolationError):
        await runtime.gateway.execute_approved(queued.output.approval_id, ctx.principal)
    assert runtime.integrations.whatsapp.outbox == []


@pytest.mark.parametrize("marketing", [False, True])
async def test_standalone_email_accepts_valid_consent_policy(marketing):
    sender = MockEmailSender()
    await EmailSendTool(sender).execute(
        {
            "to": "fixture@example.com",
            "subject": "Fictional portfolio message",
            "body": "Fictional portfolio reply",
            "is_marketing": marketing,
            "consent_marketing": marketing,
        }
    )
    assert len(sender.outbox) == 1
