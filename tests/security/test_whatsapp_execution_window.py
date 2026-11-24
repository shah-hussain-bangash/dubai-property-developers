"""The service window is checked at the provider boundary after asynchronous waits."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest

from core.exceptions.errors import PolicyViolationError
from integrations.meta.client import MockWhatsAppClient
from tools.whatsapp import policy
from tools.whatsapp.tools import WhatsAppSendTool
from workflows.runtime import build_runtime


def controlled_clock(monkeypatch):
    state = {"now": datetime(2026, 11, 24, 12, tzinfo=UTC)}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return state["now"].astimezone(tz) if tz else state["now"].replace(tzinfo=None)

    monkeypatch.setattr(policy, "datetime", Clock)
    return state


def payload(now):
    return {
        "to_e164": "+971500000001",
        "consent_whatsapp": True,
        "last_inbound_at": (now - timedelta(hours=23)).isoformat(),
        "text": "Fictional garden policy includes eight gardens.",
    }


def attach_sources(runtime, ctx, data):
    runtime.assigned_sources.add(
        ctx.tenant_id,
        "whatsapp",
        "Reviewed garden policy",
        "text",
        [data["text"]],
        customer_safe=True,
    )
    data["knowledge_citations"] = runtime.assigned_sources.tool_search(
        ctx.tenant_id, "whatsapp", "garden policy"
    )["citations"]


@pytest.mark.parametrize("supplied", [False, True])
@pytest.mark.parametrize("entry", ["approved", "invoke"])
@pytest.mark.parametrize("expires", [False, True])
async def test_waiting_for_execution_cannot_preserve_an_expired_window(
    settings, tmp_path, ctx, monkeypatch, supplied, entry, expires
):
    if supplied:
        settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    runtime = build_runtime(settings)
    await runtime.initialize()
    state = controlled_clock(monkeypatch)
    data = payload(state["now"])
    if supplied:
        attach_sources(runtime, ctx, data)
    agent = runtime.agents.get("whatsapp")
    requested = await agent.use_tool(ctx, "whatsapp.send_message", data)
    await runtime.approvals.decide(
        requested.approval_id, approved=True, decided_by=ctx.principal.subject
    )
    lock = runtime.gateway.idempotency.execution_lock(requested.idempotency_key)
    await lock.acquire()
    waiting = asyncio.Event()

    @asynccontextmanager
    async def observed_lock(key):
        assert key == requested.idempotency_key
        waiting.set()
        async with lock:
            yield

    monkeypatch.setattr(runtime.gateway.idempotency, "execution_lock", observed_lock)
    call = (
        agent.use_tool(ctx, "whatsapp.send_message", data)
        if entry == "invoke"
        else runtime.gateway.execute_approved(requested.approval_id, ctx.principal)
    )
    running = asyncio.create_task(call)
    try:
        # This event is reached only after initial validation and before lock acquisition.
        await asyncio.wait_for(waiting.wait(), timeout=2)
        state["now"] += timedelta(hours=2) if expires else timedelta(minutes=30)
        lock.release()
        if expires:
            with pytest.raises(PolicyViolationError):
                await running
            assert runtime.integrations.whatsapp.outbox == []
        else:
            result = await running
            assert result.status == "executed"
            assert len(runtime.integrations.whatsapp.outbox) == 1
    finally:
        if lock.locked():
            lock.release()
        if not running.done():
            running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        await runtime.shutdown()


async def test_window_is_rechecked_after_asynchronous_source_validation(
    settings, tmp_path, ctx, monkeypatch
):
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    runtime = build_runtime(settings)
    await runtime.initialize()
    state = controlled_clock(monkeypatch)
    data = payload(state["now"])
    attach_sources(runtime, ctx, data)
    source_check = runtime.assigned_sources.validate_message

    def delayed_source_check(*args):
        source_check(*args)
        state["now"] += timedelta(hours=2)

    monkeypatch.setattr(runtime.assigned_sources, "validate_message", delayed_source_check)
    try:
        requested = await runtime.agents.get("whatsapp").use_tool(
            ctx, "whatsapp.send_message", data
        )
        await runtime.approvals.decide(
            requested.approval_id, approved=True, decided_by=ctx.principal.subject
        )
        with pytest.raises(PolicyViolationError):
            await runtime.gateway.execute_approved(requested.approval_id, ctx.principal)
        assert runtime.integrations.whatsapp.outbox == []
    finally:
        await runtime.shutdown()


@pytest.mark.parametrize("age", [None, timedelta(hours=25), timedelta(hours=-1)])
async def test_direct_tool_execution_cannot_skip_service_window(monkeypatch, age):
    state = controlled_clock(monkeypatch)
    data = payload(state["now"])
    data["last_inbound_at"] = (state["now"] - age).isoformat() if age is not None else None
    client = MockWhatsAppClient()
    with pytest.raises(PolicyViolationError):
        await WhatsAppSendTool(client).execute(data)
    assert client.outbox == []
