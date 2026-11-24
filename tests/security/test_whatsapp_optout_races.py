"""An ordinary message cannot erase a concurrent opt-out or revive a queued reply."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from core.exceptions.errors import PolicyViolationError
from workflows.runtime import build_runtime

TEXT = "Fictional garden policy includes eight gardens."


@pytest.fixture(params=[False, True], ids=["fixture-mode", "source-only"])
async def consent_runtime(request, settings, tmp_path, ctx):
    if request.param:
        settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    runtime = build_runtime(settings)
    await runtime.initialize()
    if request.param:
        runtime.assigned_sources.add(
            ctx.tenant_id,
            "whatsapp",
            "Reviewed garden policy",
            "text",
            [TEXT],
            customer_safe=True,
        )
    try:
        yield runtime
    finally:
        await runtime.shutdown()


def message(text="What is the garden policy?", **overrides):
    return {
        "conversation_id": "fictional-optout-race",
        "from_e164": "+971500000001",
        "text": text,
        "received_at": datetime.now(UTC).isoformat(),
        "consent_whatsapp": True,
        "draft_reply": TEXT,
        "send_reply": False,
        **overrides,
    }


async def test_normal_message_cannot_replace_an_optout_with_stale_state(
    consent_runtime, ctx, monkeypatch
):
    raw = consent_runtime.deps.memory
    agent = consent_runtime.agents.get("whatsapp")
    waiting, resume = asyncio.Event(), asyncio.Event()

    async def pause_normal():
        if asyncio.current_task().get_name() == "fictional-normal-message":
            waiting.set()
            await resume.wait()

    original_set = raw.set_state

    async def paused_set(*args):
        await pause_normal()
        return await original_set(*args)

    monkeypatch.setattr(raw, "set_state", paused_set)
    # Exercise the same interleaving before and after the atomic patch API exists.
    original_update = getattr(raw, "update_state", None)
    if original_update is not None:

        async def paused_update(*args):
            await pause_normal()
            return await original_update(*args)

        monkeypatch.setattr(raw, "update_state", paused_update)

    normal = asyncio.create_task(agent.run(message(), ctx), name="fictional-normal-message")
    try:
        await asyncio.wait_for(waiting.wait(), timeout=2)
        stopped = await agent.run(message("STOP sending, unsubscribe"), ctx)
        assert stopped.status == "escalated"
        resume.set()
        result = await normal
        state = await agent.conversation_memory(ctx).get_state("fictional-optout-race")
        assert state["opted_out"] is True
        assert result.status == "escalated" and result.output.reply_mode == "no_reply"
        assert consent_runtime.integrations.whatsapp.outbox == []
    finally:
        resume.set()
        if not normal.done():
            normal.cancel()
        await asyncio.gather(normal, return_exceptions=True)


@pytest.mark.parametrize("withdrawal", ["opt-out", "consent-flag"])
async def test_queued_reply_is_blocked_when_customer_opts_out(consent_runtime, ctx, withdrawal):
    agent = consent_runtime.agents.get("whatsapp")
    queued = await agent.run(message(send_reply=True), ctx)
    assert queued.status == "pending_approval"
    if withdrawal == "opt-out":
        await agent.run(message("STOP sending, unsubscribe"), ctx)
    else:
        await agent.run(message(consent_whatsapp=False), ctx)
    await consent_runtime.approvals.decide(
        queued.output.approval_id, approved=True, decided_by=ctx.principal.subject
    )
    with pytest.raises(PolicyViolationError):
        await consent_runtime.gateway.execute_approved(queued.output.approval_id, ctx.principal)
    assert consent_runtime.integrations.whatsapp.outbox == []


async def test_other_organization_optout_does_not_cancel_own_approved_reply(consent_runtime, ctx):
    agent = consent_runtime.agents.get("whatsapp")
    queued = await agent.run(message(send_reply=True), ctx)
    other = replace(
        ctx, tenant_id="other-tenant", principal=replace(ctx.principal, tenant_id="other-tenant")
    )
    await agent.run(message("STOP sending, unsubscribe"), other)
    await consent_runtime.approvals.decide(
        queued.output.approval_id, approved=True, decided_by=ctx.principal.subject
    )
    result = await consent_runtime.gateway.execute_approved(
        queued.output.approval_id, ctx.principal
    )
    assert result.status == "executed"
    assert len(consent_runtime.integrations.whatsapp.outbox) == 1


async def test_changed_recipient_blocks_an_old_approval(consent_runtime, ctx):
    agent = consent_runtime.agents.get("whatsapp")
    queued = await agent.run(message(send_reply=True), ctx)
    await agent.run(message(from_e164="+971500000002"), ctx)
    await consent_runtime.approvals.decide(
        queued.output.approval_id, approved=True, decided_by=ctx.principal.subject
    )
    with pytest.raises(PolicyViolationError):
        await consent_runtime.gateway.execute_approved(queued.output.approval_id, ctx.principal)
    assert consent_runtime.integrations.whatsapp.outbox == []


@pytest.mark.parametrize("reference", [None, "unknown-thread", "other-only"])
async def test_payload_reference_cannot_supply_its_own_consent(consent_runtime, ctx, reference):
    agent = consent_runtime.agents.get("whatsapp")
    queued = await agent.run(message(send_reply=True), ctx)
    other = replace(
        ctx, tenant_id="other-tenant", principal=replace(ctx.principal, tenant_id="other-tenant")
    )
    await agent.run(message(conversation_id="other-only"), other)
    payload = (await consent_runtime.approvals.get(queued.output.approval_id)).payload
    if reference is None:
        payload.pop("conversation_id")
    else:
        payload["conversation_id"] = reference
    forged = await agent.use_tool(ctx, "whatsapp.send_message", payload)
    await consent_runtime.approvals.decide(
        forged.approval_id, approved=True, decided_by=ctx.principal.subject
    )
    with pytest.raises(PolicyViolationError):
        await consent_runtime.gateway.execute_approved(forged.approval_id, ctx.principal)
    assert consent_runtime.integrations.whatsapp.outbox == []


async def test_completed_reply_can_replay_after_optout_without_resending(consent_runtime, ctx):
    agent = consent_runtime.agents.get("whatsapp")
    queued = await agent.run(message(send_reply=True), ctx)
    await consent_runtime.approvals.decide(
        queued.output.approval_id, approved=True, decided_by=ctx.principal.subject
    )
    assert (
        await consent_runtime.gateway.execute_approved(queued.output.approval_id, ctx.principal)
    ).status == "executed"
    await agent.run(message("STOP sending, unsubscribe"), ctx)
    replay = await consent_runtime.gateway.execute_approved(
        queued.output.approval_id, ctx.principal
    )
    assert replay.status == "replayed" and len(consent_runtime.integrations.whatsapp.outbox) == 1
    assert "conversation_id" not in consent_runtime.integrations.whatsapp.outbox[0]


async def test_atomic_patch_preserves_other_fields_and_independent_snapshots(consent_runtime, ctx):
    memory = consent_runtime.agents.get("whatsapp").conversation_memory(ctx)
    await memory.update_state("snapshot", {"opted_out": True})
    patch = {"details": {"steps": ["original"]}}
    result = await memory.update_state("snapshot", patch)
    patch["details"]["steps"].append("input change")
    result["details"]["steps"].append("result change")
    assert await memory.get_state("snapshot") == {
        "opted_out": True,
        "details": {"steps": ["original"]},
    }
    other = replace(
        ctx, tenant_id="other-tenant", principal=replace(ctx.principal, tenant_id="other-tenant")
    )
    assert (
        await consent_runtime.agents.get("whatsapp")
        .conversation_memory(other)
        .get_state("snapshot")
        == {}
    )
