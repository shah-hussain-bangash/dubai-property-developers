"""Conversation identifiers never select another organization's or agent's memory."""

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.exceptions.errors import AuthorizationError
from core.memory.base import MemoryMessage
from knowledge.agent_data.catalogue import dataset_ids


def whatsapp(text, conversation="fictional-shared-id"):
    return {
        "conversation_id": conversation,
        "from_e164": "+971500000001",
        "text": text,
        "received_at": datetime.now(UTC).isoformat(),
        "consent_whatsapp": True,
        "draft_reply": "Fictional draft.",
        "send_reply": False,
    }


def other_organization(ctx):
    return replace(
        ctx, tenant_id="other-tenant", principal=replace(ctx.principal, tenant_id="other-tenant")
    )


async def test_opt_out_cannot_suppress_a_different_organization(runtime, ctx):
    agent = runtime.agents.get("whatsapp")
    stopped = await agent.run(whatsapp("Please unsubscribe, stop sending"), ctx)
    assert stopped.status == "escalated" and stopped.output.reply_mode == "no_reply"
    other = await agent.run(whatsapp("Fictional garden question"), other_organization(ctx))
    assert other.status == "succeeded" and other.output.reply_mode == "free_text"
    # The same organization still remembers its own withdrawal.
    repeated = await agent.run(whatsapp("Fictional garden question"), ctx)
    assert repeated.status == "escalated" and repeated.output.reply_mode == "no_reply"


async def test_sales_and_whatsapp_do_not_write_one_unscoped_history(runtime, ctx):
    conversation = "fictional-shared-id"
    await runtime.agents.get("sales_conversation").run(
        {
            "message": {
                "conversation_id": conversation,
                "channel": "web_chat",
                "direction": "inbound",
                "sender": "customer",
                "text": "Fictional sales sentinel",
            }
        },
        ctx,
    )
    await runtime.agents.get("whatsapp").run(
        whatsapp("Fictional WhatsApp sentinel", conversation), ctx
    )
    assert await runtime.deps.memory.history(conversation) == []
    for agent, expected in [
        ("sales_conversation", "Fictional sales sentinel"),
        ("whatsapp", "Fictional WhatsApp sentinel"),
    ]:
        history = await runtime.agents.get(agent).conversation_memory(ctx).history(conversation)
        assert [message.content for message in history] == [expected]


async def test_mismatched_identity_fails_before_writing_memory(runtime, ctx):
    mismatched = replace(ctx, tenant_id="other-tenant")
    result = await runtime.agents.get("whatsapp").run(
        whatsapp("Fictional blocked message"), mismatched
    )
    assert result.status == "failed" and result.error.code == "forbidden"
    assert await runtime.deps.memory.history("fictional-shared-id") == []


@pytest.mark.parametrize("agent", dataset_ids())
async def test_every_agent_memory_scope_keeps_history_and_state_separate(runtime, ctx, agent):
    conversation = "fictional-shared-id"
    scopes = [
        (tenant_ctx, owner)
        for tenant_ctx in [ctx, other_organization(ctx)]
        for owner in dataset_ids()
    ]
    for tenant_ctx, owner in scopes:
        memory = runtime.agents.get(owner).conversation_memory(tenant_ctx)
        marker = f"Fictional memory for {tenant_ctx.tenant_id}/{owner}"
        await memory.append(conversation, MemoryMessage(role="customer", content=marker))
        await memory.set_state(conversation, {"marker": marker})
    memory = runtime.agents.get(agent).conversation_memory(ctx)
    expected = f"Fictional memory for {ctx.tenant_id}/{agent}"
    assert [m.content for m in await memory.history(conversation)] == [expected]
    assert await memory.get_state(conversation) == {"marker": expected}
    assert await memory.history("different-conversation") == []
    assert await memory.get_state("different-conversation") == {}
    # A second operator in the same organization shares the same authorized scope.
    colleague = replace(ctx, principal=replace(ctx.principal, subject="fictional-colleague"))
    assert await runtime.agents.get(agent).conversation_memory(colleague).get_state(
        conversation
    ) == {"marker": expected}


async def test_unscoped_legacy_memory_is_not_borrowed_or_deleted(runtime, ctx):
    raw = runtime.deps.memory
    await raw.append(
        "legacy-id", MemoryMessage(role="customer", content="Unassigned fictional history")
    )
    await raw.set_state("legacy-id", {"legacy_marker": "unassigned"})
    view = runtime.agents.get("whatsapp").conversation_memory(ctx)
    assert await view.history("legacy-id") == [] and await view.get_state("legacy-id") == {}
    assert (await raw.history("legacy-id"))[0].content == "Unassigned fictional history"
    assert await raw.get_state("legacy-id") == {"legacy_marker": "unassigned"}
    with pytest.raises(AuthorizationError):
        view.scoped("other-tenant", "whatsapp")


async def test_delimiter_or_namespace_like_ids_cannot_select_another_scope(runtime, ctx):
    first = replace(
        ctx, tenant_id="team:whatsapp", principal=replace(ctx.principal, tenant_id="team:whatsapp")
    )
    second = replace(ctx, tenant_id="team", principal=replace(ctx.principal, tenant_id="team"))
    sales = runtime.agents.get("sales_conversation").conversation_memory(first)
    wa = runtime.agents.get("whatsapp").conversation_memory(second)
    await sales.set_state("customer", {"marker": "sales-only"})
    await wa.set_state("sales_conversation:customer", {"marker": "whatsapp-only"})
    assert await sales.get_state("customer") == {"marker": "sales-only"}
    assert await wa.get_state("sales_conversation:customer") == {"marker": "whatsapp-only"}
    assert await wa.get_state("agent-memory:v1:customer") == {}


async def test_backend_without_scoping_fails_closed_before_writing(runtime, ctx):
    backend = SimpleNamespace(append=AsyncMock(), get_state=AsyncMock())
    runtime.deps.memory = backend
    result = await runtime.agents.get("whatsapp").run(whatsapp("Fictional blocked message"), ctx)
    assert result.status == "failed" and result.error.code == "forbidden"
    backend.append.assert_not_awaited()
