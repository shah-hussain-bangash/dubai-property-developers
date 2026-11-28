"""An identical action cannot borrow another agent's approval or replay result."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from core.exceptions.errors import PolicyViolationError
from integrations.meta.client import MockWhatsAppClient
from knowledge.agent_data.catalogue import dataset_ids
from tools.base import ToolCallContext, ToolGateway, ToolRegistry
from tools.email.sender import MockEmailSender
from tools.email.tools import EmailSendTool
from tools.whatsapp.tools import WhatsAppSendTool

PAYLOAD = {
    "to": "fixture@example.com",
    "subject": "Fictional portfolio policy",
    "body": "Fictional garden policy includes eight gardens.",
    "agent_id": "caller-cannot-select-owner",
}


def context(manager, agent, tool="email.send"):
    return ToolCallContext(
        manager, manager.tenant_id, "fictional-agent-actions", agent, frozenset({tool})
    )


@pytest.mark.parametrize("agent", dataset_ids())
async def test_each_agent_has_its_own_action_approval(manager, agent):
    registry = ToolRegistry()
    registry.register(EmailSendTool(MockEmailSender()))
    gateway = ToolGateway(registry)
    first = await gateway.invoke(context(manager, None), "email.send", PAYLOAD)
    second = await gateway.invoke(context(manager, agent), "email.send", PAYLOAD)
    assert first.approval_id != second.approval_id
    assert first.idempotency_key != second.idempotency_key
    assert (await gateway.approvals.get(second.approval_id)).requested_by_agent == agent
    retry = await gateway.invoke(context(manager, agent), "email.send", dict(PAYLOAD))
    assert retry.approval_id == second.approval_id


@pytest.mark.parametrize("stage", ["pending", "approved", "executed"])
async def test_another_agent_cannot_inherit_action_lifecycle(manager, stage):
    sender = MockEmailSender()
    registry = ToolRegistry()
    registry.register(EmailSendTool(sender))
    gateway = ToolGateway(registry)
    first = await gateway.invoke(context(manager, "email"), "email.send", PAYLOAD)
    if stage != "pending":
        await gateway.approvals.decide(first.approval_id, approved=True, decided_by=manager.subject)
    if stage == "executed":
        await gateway.execute_approved(first.approval_id, manager)
    other = await gateway.invoke(context(manager, "followup"), "email.send", PAYLOAD)
    assert other.status == "pending_approval"
    assert other.approval_id != first.approval_id
    assert len(sender.outbox) == (1 if stage == "executed" else 0)


@pytest.mark.parametrize("channel", ["email", "whatsapp"])
async def test_copied_source_payload_cannot_replay_another_agents_send(
    settings, tmp_path, manager, channel
):
    from workflows.runtime import build_runtime

    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    runtime = build_runtime(settings)
    await runtime.initialize()
    try:
        runtime.assigned_sources.add(
            manager.tenant_id,
            channel,
            PAYLOAD["subject"],
            "text",
            [PAYLOAD["body"]],
            customer_safe=True,
        )
        citations = runtime.assigned_sources.tool_search(
            manager.tenant_id, channel, "garden policy", True
        )["citations"]
        tool = "email.send" if channel == "email" else "whatsapp.send_message"
        payload = (
            dict(PAYLOAD)
            if channel == "email"
            else {
                "to_e164": "+971500000001",
                "text": PAYLOAD["body"],
                "consent_whatsapp": True,
                "last_inbound_at": datetime.now(UTC).isoformat(),
                "conversation_id": "fictional-agent-actions",
            }
        )
        payload["knowledge_citations"] = citations
        original = context(manager, channel, tool)
        if channel == "whatsapp":
            await runtime.deps.memory.scoped(manager.tenant_id, channel).update_state(
                payload["conversation_id"],
                {"consent_whatsapp": True, "from_e164": payload["to_e164"]},
            )
        queued = await runtime.gateway.invoke(original, tool, payload)
        await runtime.approvals.decide(
            queued.approval_id, approved=True, decided_by=manager.subject
        )
        first = await runtime.gateway.execute_approved(queued.approval_id, manager)
        assert first.status == "executed"
        other = await runtime.gateway.invoke(replace(original, agent_id="followup"), tool, payload)
        assert other.status == "pending_approval"
        await runtime.approvals.decide(other.approval_id, approved=True, decided_by=manager.subject)
        with pytest.raises(PolicyViolationError):
            await runtime.gateway.execute_approved(other.approval_id, manager)
        outbox = (
            runtime.email_sender.outbox
            if channel == "email"
            else runtime.integrations.whatsapp.outbox
        )
        assert len(outbox) == 1
    finally:
        await runtime.shutdown()


@pytest.mark.parametrize("channel", ["email", "whatsapp"])
async def test_provider_keys_separate_agents_and_preserve_same_agent_retries(
    manager, channel, monkeypatch
):
    keys = []
    if channel == "email":
        client = MockEmailSender()
        tool = EmailSendTool(client)
        payload = dict(PAYLOAD)
        method = "send"
    else:
        client = MockWhatsAppClient()
        tool = WhatsAppSendTool(client)
        payload = {
            "to_e164": "+971500000001",
            "text": PAYLOAD["body"],
            "last_inbound_at": datetime.now(UTC).isoformat(),
            "consent_whatsapp": True,
        }
        method = "send_text"
    original = getattr(client, method)

    async def capture(**kwargs):
        keys.append(kwargs["idempotency_key"])
        return await original(**kwargs)

    monkeypatch.setattr(client, method, capture)
    for agent in [channel, "followup", channel]:
        await tool.execute_with_context(payload, context(manager, agent, tool.spec.name))
    assert keys[0] == keys[2]
    assert keys[0] != keys[1]
    if channel == "whatsapp":
        assert len(client.outbox) == 2


async def test_unscoped_call_can_replay_its_existing_legacy_key(manager):
    sender = MockEmailSender()
    registry = ToolRegistry()
    registry.register(EmailSendTool(sender))
    gateway = ToolGateway(registry)
    # Fixed pre-change key for this fictional organization/action/payload.
    legacy = "email.send:ebde19dd1243ff3268841255792f5640215cb645"
    await gateway.idempotency.put(legacy, {"message_id": "fictional-legacy-result"}, 60)
    result = await gateway.invoke(context(manager, None), "email.send", PAYLOAD)
    assert result.status == "replayed"
    assert result.data["message_id"] == "fictional-legacy-result"
    assert sender.outbox == []
