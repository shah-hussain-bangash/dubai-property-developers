"""Untrusted timestamps cannot open a free-text service window or bypass validation."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from core.exceptions.errors import DomainValidationError, PolicyViolationError
from integrations.meta.client import MockWhatsAppClient
from tools.whatsapp.policy import is_within_service_window
from tools.whatsapp.tools import WhatsAppSendTool
from workflows.runtime import build_runtime

NOW = datetime(2026, 11, 24, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "age,expected",
    [
        (timedelta(0), True),
        (timedelta(microseconds=-1), False),
        (timedelta(hours=-1), False),
        (timedelta(days=-365), False),
        (timedelta(hours=23), True),
        (timedelta(hours=24), True),
        (timedelta(hours=24, microseconds=1), False),
        (timedelta(hours=25), False),
    ],
)
def test_service_window_has_both_a_lower_and_upper_bound(age, expected):
    assert is_within_service_window(NOW - age, NOW) is expected


@pytest.mark.parametrize("naive_now", [False, True])
def test_service_window_normalizes_equivalent_timezone_representations(naive_now):
    now = NOW.replace(tzinfo=None) if naive_now else NOW
    inbound = (NOW - timedelta(hours=2)).astimezone(timezone(timedelta(hours=4)))
    assert is_within_service_window(inbound, now)
    assert is_within_service_window((NOW - timedelta(hours=2)).replace(tzinfo=None), now)
    assert not is_within_service_window(None, now)


@pytest.mark.parametrize("invalid", ["not-a-timestamp", "2026-99-99T00:00:00Z", 123, {}, True])
def test_malformed_send_timestamp_is_a_validation_error(invalid):
    client = MockWhatsAppClient()
    with pytest.raises(DomainValidationError):
        WhatsAppSendTool(client).validate(
            {
                "to_e164": "+971500000001",
                "consent_whatsapp": True,
                "last_inbound_at": invalid,
                "text": "Fictional timestamp check.",
            }
        )
    assert client.outbox == []


async def test_future_send_timestamp_is_rejected_before_approval(runtime, ctx):
    with pytest.raises(PolicyViolationError):
        await runtime.agents.get("whatsapp").use_tool(
            ctx,
            "whatsapp.send_message",
            {
                "to_e164": "+971500000001",
                "consent_whatsapp": True,
                "last_inbound_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "text": "Fictional timestamp check.",
            },
        )
    assert await runtime.approvals.list_pending(ctx.tenant_id) == []
    assert runtime.integrations.whatsapp.outbox == []


@pytest.mark.parametrize("agent", ["whatsapp", "followup"])
async def test_future_timestamp_cannot_override_supplied_source_guards(
    settings, tmp_path, ctx, agent
):
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    runtime = build_runtime(settings)
    await runtime.initialize()
    try:
        runtime.assigned_sources.add(
            ctx.tenant_id,
            agent,
            "Reviewed garden policy",
            "text",
            ["Fictional garden policy includes eight gardens."],
            customer_safe=True,
        )
        now = datetime.now(UTC)
        future = (now + timedelta(days=1)).isoformat()
        if agent == "whatsapp":
            payload = {
                "conversation_id": "fictional-future-event",
                "from_e164": "+971500000001",
                "text": "What is the garden policy?",
                "received_at": future,
                "consent_whatsapp": True,
                "send_reply": True,
            }
        else:
            payload = {
                "dispatch": True,
                "tasks": [
                    {
                        "task_id": "fictional-future-task",
                        "lead_id": "fictional-lead",
                        "contact_first_name": "Fictional Visitor",
                        "channel": "whatsapp",
                        "due_at": (now - timedelta(hours=1)).isoformat(),
                        "to_e164": "+971500000001",
                        "consent_whatsapp": True,
                        "last_inbound_at": future,
                        "knowledge_query": "garden policy",
                    }
                ],
            }
        result = await runtime.agents.get(agent).run(payload, ctx)
        assert result.status == "escalated"
        if agent == "whatsapp":
            assert result.output.reply_mode == "no_reply" and result.output.reply_text is None
        else:
            assert result.output.actions == [] and result.output.escalations
        assert await runtime.approvals.list_pending(ctx.tenant_id) == []
        assert runtime.integrations.whatsapp.outbox == []
    finally:
        await runtime.shutdown()
