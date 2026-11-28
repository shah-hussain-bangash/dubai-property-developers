"""Fictional bookings retain account, approved event and time boundaries."""

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from core.exceptions.errors import AuthorizationError, DomainValidationError
from core.policies.approvals import ApprovalRequest
from core.resilience.idempotency import InMemoryIdempotencyStore, make_idempotency_key
from integrations.google.client import MockCalendarClient
from tools.base import ToolCallContext
from tools.calendar.tools import CalendarCreateEventTool

EVENT = {
    "summary": "Fictional portfolio viewing",
    "start": "2030-01-01T10:00:00+04:00",
    "end": "2030-01-01T11:00:00+04:00",
    "attendees": ["fixture.one@example.com"],
    "idempotency_key": "fictional-shared-viewing-key",
}


def context(manager, **changes):
    return replace(
        ToolCallContext(manager, manager.tenant_id, "fictional-calendar-boundary"), **changes
    )


async def approve(runtime, manager, event):
    queued = await runtime.gateway.invoke(context(manager), "calendar.create_event", event)
    assert queued.status == "pending_approval"
    await runtime.approvals.decide(queued.approval_id, approved=True, decided_by=manager.subject)
    return queued.approval_id, await runtime.gateway.execute_approved(queued.approval_id, manager)


@pytest.mark.parametrize("changed", ["attendees", "end", "description"])
async def test_different_approved_event_is_not_suppressed(runtime, manager, changed):
    _, first = await approve(runtime, manager, EVENT)
    values = {
        "attendees": ["fixture.two@example.com"],
        "end": "2030-01-01T12:00:00+04:00",
        "description": "Different fictional viewing instructions",
    }
    _, second = await approve(runtime, manager, {**EVENT, changed: values[changed]})
    assert first.data["event_id"] != second.data["event_id"]
    assert len(runtime.integrations.calendar.events) == 2


async def test_identical_booking_retries_keep_provider_dedup_after_cache_loss(runtime, manager):
    approval, first = await approve(runtime, manager, EVENT)
    runtime.gateway.idempotency = InMemoryIdempotencyStore()
    second = await runtime.gateway.execute_approved(approval, manager)
    assert first.data == second.data
    assert len(runtime.integrations.calendar.events) == 1


@pytest.mark.parametrize("cached", [False, True])
async def test_other_organization_cannot_request_or_replay_booking(
    runtime, manager, monkeypatch, cached
):
    other = replace(manager, tenant_id="other-org")
    foreign = context(other)
    if cached:
        key = make_idempotency_key("calendar.create_event", EVENT, scope=other.tenant_id)
        await runtime.gateway.idempotency.put(key, {"event_id": "fictional-old-foreign-event"}, 60)
    client = AsyncMock(return_value="fictional-id")
    monkeypatch.setattr(runtime.integrations.calendar, "create_event", client)
    with pytest.raises(AuthorizationError):
        await runtime.gateway.invoke(foreign, "calendar.create_event", EVENT)
    assert await runtime.approvals.list_pending(other.tenant_id) == []
    client.assert_not_awaited()


async def test_legacy_foreign_approval_cannot_override_calendar_owner(
    runtime, manager, monkeypatch
):
    other = replace(manager, tenant_id="other-org")
    request = await runtime.approvals.create(
        ApprovalRequest(
            tenant_id=other.tenant_id,
            tool_name="calendar.create_event",
            action_category="calendar_write",
            requested_by=other.subject,
            reason="Fictional old approval",
            payload=EVENT,
            idempotency_key="fictional-old-foreign-calendar-key",
        )
    )
    await runtime.approvals.decide(request.approval_id, approved=True, decided_by=other.subject)
    cached = AsyncMock(return_value={"event_id": "fictional-old-result"})
    monkeypatch.setattr(runtime.gateway.idempotency, "get", cached)
    with pytest.raises(AuthorizationError):
        await runtime.gateway.execute_approved(request.approval_id, other)
    cached.assert_not_awaited()
    assert runtime.integrations.calendar.events == []


async def test_bound_calendar_requires_context(runtime):
    with pytest.raises(AuthorizationError):
        await runtime.tools.get("calendar.create_event").execute(EVENT)
    assert runtime.integrations.calendar.events == []


async def test_contextual_calendar_requires_account_binding(manager):
    with pytest.raises(AuthorizationError):
        await CalendarCreateEventTool(MockCalendarClient()).execute_with_context(
            EVENT, context(manager)
        )


@pytest.mark.parametrize(
    "start,end",
    [
        (None, EVENT["end"]),
        (123, EVENT["end"]),
        ([], EVENT["end"]),
        ("not-a-time", EVENT["end"]),
        (EVENT["start"], "not-a-time"),
        (EVENT["start"], EVENT["start"]),
        (EVENT["end"], EVENT["start"]),
        ("2030-01-01T10:00:00", "2030-01-01T11:00:00"),
        ("2030-01-01T10:00:00", EVENT["end"]),
    ],
)
@pytest.mark.parametrize("entry", ["gateway", "standalone"])
async def test_invalid_or_ambiguous_time_cannot_book(runtime, manager, start, end, entry):
    event = {**EVENT, "start": start, "end": end}
    client = MockCalendarClient()
    with pytest.raises(DomainValidationError):
        if entry == "standalone":
            await CalendarCreateEventTool(client).execute(event)
        else:
            await runtime.gateway.invoke(context(manager), "calendar.create_event", event)
    assert client.events == runtime.integrations.calendar.events == []
    assert await runtime.approvals.list_pending(manager.tenant_id) == []


async def test_legacy_standalone_key_is_preserved(monkeypatch):
    client = MockCalendarClient()
    send = AsyncMock(return_value="fictional-event-id")
    monkeypatch.setattr(client, "create_event", send)
    await CalendarCreateEventTool(client).execute(EVENT)
    assert send.await_args.kwargs["idempotency_key"] == EVENT["idempotency_key"]


async def test_distinct_trusted_agent_actions_have_distinct_provider_keys(runtime, manager):
    # Synthetic contexts exercise the tool boundary without granting real agents new tools.
    results = []
    for agent in ["fictional-booking-a", "fictional-booking-b"]:
        own = context(manager, agent_id=agent, allowed_tools=frozenset({"calendar.create_event"}))
        queued = await runtime.gateway.invoke(own, "calendar.create_event", EVENT)
        await runtime.approvals.decide(
            queued.approval_id, approved=True, decided_by=manager.subject
        )
        results.append(await runtime.gateway.execute_approved(queued.approval_id, manager))
    assert results[0].data["event_id"] != results[1].data["event_id"]
    assert len(runtime.integrations.calendar.events) == 2
    keys = list(runtime.integrations.calendar._seen)
    assert len(keys) == 2 and keys[0] != keys[1]
    assert all(EVENT["idempotency_key"] not in key and "@example.com" not in key for key in keys)


async def test_direct_context_cannot_spoof_calendar_owner(runtime, manager):
    foreign = replace(manager, tenant_id="other-org")
    forged = context(foreign, tenant_id=manager.tenant_id)
    with pytest.raises(AuthorizationError):
        await runtime.tools.get("calendar.create_event").execute_with_context(EVENT, forged)
    assert runtime.integrations.calendar.events == []


async def test_calendar_binds_configured_workspace_and_preserves_explicit_offset(settings, manager):
    from datetime import timedelta

    from workflows.runtime import build_runtime

    settings.default_tenant_id = "fictional-calendar-owner"
    runtime = build_runtime(settings)
    await runtime.initialize()
    try:
        owner = replace(manager, tenant_id=settings.default_tenant_id)
        await approve(runtime, owner, EVENT)
        assert runtime.integrations.calendar.events[0]["start"].utcoffset() == timedelta(hours=4)
        with pytest.raises(AuthorizationError):
            await runtime.gateway.invoke(context(manager), "calendar.create_event", EVENT)
    finally:
        await runtime.shutdown()
