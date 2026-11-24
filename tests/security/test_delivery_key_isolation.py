"""Provider keys must retain trusted tenant and exact approved-message boundaries."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from core.resilience.idempotency import InMemoryIdempotencyStore
from integrations.meta.client import MockWhatsAppClient
from tools.email.sender import MockEmailSender
from tools.email.tools import EmailSendTool
from tools.whatsapp.tools import WhatsAppSendTool
from workflows.runtime import build_runtime

TEXT = "Fictional garden policy includes eight gardens."


@pytest.fixture(params=[False, True], ids=["fixture-mode", "source-only"])
async def delivery_runtime(request, settings, tmp_path):
    if request.param:
        settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    runtime = build_runtime(settings)
    await runtime.initialize()
    try:
        yield runtime
    finally:
        await runtime.shutdown()


def sources(runtime, ctx, agent):
    if runtime.assigned_sources is not None:
        runtime.assigned_sources.add(
            ctx.tenant_id, agent, "Reviewed garden policy", "text", [TEXT], customer_safe=True
        )


async def approve(runtime, ctx, approval):
    await runtime.approvals.decide(approval, approved=True, decided_by=ctx.principal.subject)
    return await runtime.gateway.execute_approved(approval, ctx.principal)


@pytest.mark.parametrize("sender", ["whatsapp", "email"])
async def test_same_event_in_two_organizations_has_separate_provider_keys(
    delivery_runtime, ctx, monkeypatch, sender
):
    runtime = delivery_runtime
    other = replace(
        ctx, tenant_id="other-tenant", principal=replace(ctx.principal, tenant_id="other-tenant")
    )
    keys = []
    if sender == "whatsapp":
        client = runtime.integrations.whatsapp
        original = client._record

        def capture(key, message):
            keys.append(key)
            return original(key, message)

        monkeypatch.setattr(client, "_record", capture)
    else:
        original_send = runtime.email_sender.send

        async def capture_email(**kwargs):
            keys.append(kwargs["idempotency_key"])
            return await original_send(**kwargs)

        monkeypatch.setattr(runtime.email_sender, "send", capture_email)
    stamp = datetime.now(UTC).isoformat()
    results, snapshots = [], []
    for tenant_ctx in [ctx, other]:
        sources(runtime, tenant_ctx, sender)
        if sender == "whatsapp":
            payload = {
                "conversation_id": "fictional-shared-event",
                "received_at": stamp,
                "from_e164": "+971500000001",
                "text": "What is the garden policy?",
                "consent_whatsapp": True,
                "draft_reply": TEXT,
                "send_reply": True,
            }
        else:
            payload = {
                "mode": "send",
                "template": "lead_acknowledgement",
                "knowledge_query": "garden policy",
                "recipient_email": "fixture@example.com",
            }
        queued = await runtime.agents.get(sender).run(payload, tenant_ctx)
        assert queued.status == "pending_approval"
        snapshots.append((await runtime.approvals.get(queued.output.approval_id)).payload)
        results.append(await approve(runtime, tenant_ctx, queued.output.approval_id))
    if runtime.assigned_sources is None:
        assert snapshots[0] == snapshots[1]
    sent = (
        runtime.integrations.whatsapp.outbox
        if sender == "whatsapp"
        else runtime.email_sender.outbox
    )
    assert len(sent) == 2
    assert results[0].data["message_id"] != results[1].data["message_id"]
    assert len(keys) == 2 and all(keys) and keys[0] != keys[1]
    assert all("fictional-shared-event" not in key and "@example.com" not in key for key in keys)


async def test_identical_approved_payload_retains_provider_dedup_after_cache_loss(
    delivery_runtime, ctx
):
    runtime = delivery_runtime
    sources(runtime, ctx, "whatsapp")
    queued = await runtime.agents.get("whatsapp").run(
        {
            "conversation_id": "fictional-stable-event",
            "received_at": datetime.now(UTC).isoformat(),
            "from_e164": "+971500000001",
            "text": "What is the garden policy?",
            "consent_whatsapp": True,
            "draft_reply": TEXT,
            "send_reply": True,
        },
        ctx,
    )
    first = await approve(runtime, ctx, queued.output.approval_id)
    runtime.gateway.idempotency = InMemoryIdempotencyStore()
    retry = await runtime.gateway.execute_approved(queued.output.approval_id, ctx.principal)
    assert retry.data["message_id"] == first.data["message_id"]
    assert len(runtime.integrations.whatsapp.outbox) == 1


async def test_reused_followup_task_id_cannot_suppress_another_approved_recipient(
    delivery_runtime, ctx
):
    runtime = delivery_runtime
    sources(runtime, ctx, "followup")
    now = datetime.now(UTC)
    for index in range(2):
        queued = await runtime.agents.get("followup").run(
            {
                "dispatch": True,
                "tasks": [
                    {
                        "task_id": "fictional-common-task",
                        "lead_id": "fictional-lead",
                        "contact_first_name": "Fictional Visitor",
                        "channel": "whatsapp",
                        "due_at": (now - timedelta(hours=1)).isoformat(),
                        "last_inbound_at": now.isoformat(),
                        "to_e164": f"+97150000000{index + 1}",
                        "consent_whatsapp": True,
                        "knowledge_query": "garden policy",
                    }
                ],
            },
            ctx,
        )
        assert queued.status == "pending_approval"
        await approve(runtime, ctx, queued.output.actions[0].approval_id)
    assert {message["to"] for message in runtime.integrations.whatsapp.outbox} == {
        "+971500000001",
        "+971500000002",
    }


@pytest.mark.parametrize("sender", ["whatsapp", "email"])
async def test_standalone_tools_preserve_explicit_legacy_keys(monkeypatch, sender):
    keys = []
    if sender == "whatsapp":
        client = MockWhatsAppClient()
        original = client._record

        def capture(key, message):
            keys.append(key)
            return original(key, message)

        monkeypatch.setattr(client, "_record", capture)
        await WhatsAppSendTool(client).execute(
            {
                "to_e164": "+971500000001",
                "consent_whatsapp": True,
                "text": TEXT,
                "last_inbound_at": datetime.now(UTC).isoformat(),
                "idempotency_key": "fictional-legacy-key",
            }
        )
    else:
        client = MockEmailSender()
        original_send = client.send

        async def capture_email(**kwargs):
            keys.append(kwargs["idempotency_key"])
            return await original_send(**kwargs)

        monkeypatch.setattr(client, "send", capture_email)
        await EmailSendTool(client).execute(
            {
                "to": "fixture@example.com",
                "subject": "Fictional",
                "body": TEXT,
                "idempotency_key": "fictional-legacy-key",
            }
        )
    assert keys == ["fictional-legacy-key"]
