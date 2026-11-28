"""Diagnostic audit reads cannot rewrite retained records or their organization."""

import secrets
from dataclasses import replace

import pytest

from core.events.audit import AuditEvent, InMemoryAuditSink
from core.exceptions.errors import AuthorizationError
from core.security.redaction import REDACTED
from tools.base import ToolCallContext


def event(**changes):
    return AuditEvent(
        tenant_id="owner-org",
        actor="fictional-actor",
        action="fictional.action",
        resource_type="fixture",
        resource_id="fictional-resource",
        outcome="executed",
        details={"nested": {"labels": ["original"]}},
        **changes,
    )


@pytest.mark.parametrize("field", ["tenant_id", "actor", "outcome", "resource_id", "details"])
async def test_returned_record_edits_do_not_change_the_audit_trail(field):
    sink = InMemoryAuditSink()
    original = event()
    await sink.record(original)
    expected = sink.events[0].model_copy(deep=True)
    view = sink.events[0]
    if field == "details":
        view.details["nested"]["labels"].append("changed")
    else:
        setattr(view, field, "changed")
    assert sink.events == [expected]


@pytest.mark.parametrize("operation", ["clear", "pop", "append"])
async def test_returned_list_edits_cannot_delete_or_insert_audit_records(operation):
    sink = InMemoryAuditSink()
    original = event()
    await sink.record(original)
    expected = sink.events[0].model_copy(deep=True)
    view = sink.events
    if operation == "append":
        view.append(event())
    else:
        getattr(view, operation)()
    assert sink.events == [expected]


async def test_input_models_are_detached_and_read_views_are_independent():
    sink = InMemoryAuditSink()
    original = event()
    await sink.record(original)
    original.tenant_id = "other-org"
    original.details["nested"]["labels"].clear()
    first, second = sink.events, sink.events
    assert first[0].tenant_id == "owner-org"
    assert first[0].details == {"nested": {"labels": ["original"]}}
    assert first[0] is not second[0]


async def test_redaction_record_order_and_identifiers_remain_intact():
    sink = InMemoryAuditSink()
    token = secrets.token_hex(16)
    first = event()
    first.details = {"authorization": "Bearer " + token, "contact": "fictional.person@example.com"}
    second = event()
    await sink.record(first)
    await sink.record(second)
    saved = sink.events
    assert [item.audit_id for item in saved] == [first.audit_id, second.audit_id]
    assert saved[0].occurred_at == first.occurred_at
    assert saved[0].details["authorization"] == REDACTED
    assert saved[0].details["contact"] == "f***@example.com"
    assert token not in saved[0].model_dump_json()
    assert token in first.details["authorization"]


async def test_denied_cross_organization_calls_are_attributed_to_authenticated_owner(
    runtime, manager
):
    for owner in [manager, replace(manager, tenant_id="another-actor-org")]:
        ctx = ToolCallContext(
            owner,
            "requested-foreign-org",
            "fictional-audit-owner",
            "crm",
            frozenset({"crm.find_leads"}),
        )
        with pytest.raises(AuthorizationError):
            await runtime.gateway.invoke(ctx, "crm.find_leads", {"email": "fixture@example.com"})
        saved = runtime.audit.events[-1]
        assert saved.tenant_id == owner.tenant_id
        assert saved.actor == owner.subject + "/agent:crm"
        assert saved.outcome == "denied"
    assert len(runtime.audit.events) == 2
    assert runtime.integrations.crm.leads == {}


@pytest.mark.parametrize("kind", ["execution", "approval"])
async def test_normal_owned_tool_actions_keep_their_audit_fields(runtime, manager, kind):
    if kind == "execution":
        name = "crm.create_lead"
        payload = {
            "local_lead_id": "fictional-owned-id",
            "data": {"lastName": "Fictional visitor", "emailAddress": "fixture@example.com"},
        }
        expected = "executed"
    else:
        name = "email.send"
        payload = {
            "to": "fixture@example.com",
            "subject": "Fictional message",
            "body": "Fictional portfolio text",
        }
        expected = "pending_approval"
    ctx = ToolCallContext(
        manager, manager.tenant_id, "fictional-normal-audit", "fixture-agent", frozenset({name})
    )
    result = await runtime.gateway.invoke(ctx, name, payload)
    assert result.status == expected
    saved = runtime.audit.events[-1]
    assert saved.tenant_id == manager.tenant_id
    assert saved.actor == manager.subject + "/agent:fixture-agent"
    assert saved.action == "tool:" + name and saved.outcome == expected
    assert saved.correlation_id == ctx.correlation_id
    assert runtime.email_sender.outbox == []
