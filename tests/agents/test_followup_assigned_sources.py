"""Follow-up planning and dispatch cannot bypass assigned-source boundaries."""

from datetime import UTC, datetime, timedelta

import pytest

from workflows.runtime import build_runtime

TEXT = "Fictional garden follow-up policy offers a viewing on request."


@pytest.fixture
async def supplied_runtime(settings, tmp_path):
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    runtime = build_runtime(settings)
    await runtime.initialize()
    try:
        yield runtime
    finally:
        assert runtime.email_sender.outbox == []
        assert runtime.integrations.whatsapp.outbox == []
        await runtime.shutdown()


def task(channel="email", **overrides):
    now = datetime.now(UTC)
    return {
        "task_id": "fictional-due-task",
        "lead_id": "fictional-lead",
        "contact_first_name": "Fictional Visitor",
        "channel": channel,
        "due_at": (now - timedelta(hours=1)).isoformat(),
        "email": "fixture@example.com",
        "to_e164": "+971500000001",
        "consent_whatsapp": True,
        "last_inbound_at": (now - timedelta(hours=2)).isoformat(),
        "knowledge_query": "garden follow-up policy",
        **overrides,
    }


def add(runtime, ctx, source="approved"):
    if source == "missing":
        return None
    return runtime.assigned_sources.add(
        "other-tenant" if source == "other-tenant" else ctx.tenant_id,
        "email" if source == "other-agent" else "followup",
        "Reviewed follow-up policy",
        "text",
        ["Fictional telescope calibration manual." if source == "unrelated" else TEXT],
        customer_safe=source != "staff",
    )


@pytest.mark.parametrize("channel", ["email", "whatsapp"])
@pytest.mark.parametrize("source", ["missing", "staff", "other-agent", "other-tenant", "unrelated"])
async def test_followup_refuses_unapproved_or_foreign_material(
    supplied_runtime, ctx, channel, source
):
    add(supplied_runtime, ctx, source)
    result = await supplied_runtime.agents.get("followup").run(
        {"tasks": [task(channel)], "dispatch": True}, ctx
    )
    assert result.status == "escalated"
    assert result.output.actions == [] and len(result.output.escalations) == 1
    assert await supplied_runtime.approvals.list_pending(ctx.tenant_id) == []


@pytest.mark.parametrize("channel", ["email", "whatsapp"])
async def test_followup_requires_an_explicit_source_query(supplied_runtime, ctx, channel):
    add(supplied_runtime, ctx)
    result = await supplied_runtime.agents.get("followup").run(
        {"tasks": [task(channel, knowledge_query=None)]}, ctx
    )
    assert result.status == "escalated" and result.output.actions == []


@pytest.mark.parametrize("channel", ["email", "whatsapp"])
@pytest.mark.parametrize("dispatch", [False, True])
async def test_followup_quotes_own_source_with_optional_approval_request(
    supplied_runtime, ctx, channel, dispatch
):
    source = add(supplied_runtime, ctx)
    agent = supplied_runtime.agents.get("followup")
    result = await agent.run({"tasks": [task(channel)], "dispatch": dispatch}, ctx)
    assert result.status == ("pending_approval" if dispatch else "succeeded")
    action = result.output.actions[0]
    assert action.draft_text == TEXT and action.requires_approval
    assert action.template is None
    assert [c.excerpt for c in action.citations] == [TEXT]
    assert action.citations[0].document_id == f"{ctx.tenant_id}:{source['id']}"
    pending = await supplied_runtime.approvals.list_pending(ctx.tenant_id)
    assert len(pending) == int(dispatch)
    if dispatch:
        assert action.approval_id and action.send_status == "pending_approval"
        payload = pending[0].payload
        if channel == "email":
            assert payload["body"] == TEXT and payload["subject"] == "Reviewed follow-up policy"
        else:
            assert payload["text"] == TEXT and "template_name" not in payload

    supplied_runtime.assigned_sources.remove(ctx.tenant_id, "followup", source["id"])
    repeated = await agent.run({"tasks": [task(channel)]}, ctx)
    assert repeated.status == "escalated" and repeated.output.actions == []


@pytest.mark.parametrize("last_inbound", [None, "old"])
async def test_followup_never_substitutes_an_unverified_whatsapp_template(
    supplied_runtime, ctx, last_inbound
):
    add(supplied_runtime, ctx)
    when = (datetime.now(UTC) - timedelta(days=2)).isoformat() if last_inbound else None
    result = await supplied_runtime.agents.get("followup").run(
        {"tasks": [task("whatsapp", last_inbound_at=when)], "dispatch": True}, ctx
    )
    assert result.status == "escalated" and result.output.actions == []
    assert await supplied_runtime.approvals.list_pending(ctx.tenant_id) == []


async def test_source_approval_does_not_override_followup_task_guards(supplied_runtime, ctx):
    add(supplied_runtime, ctx)
    tasks = [
        task(task_id="closed", status="closed"),
        task(task_id="replied", customer_replied_since=True),
        task(task_id="future", due_at=(datetime.now(UTC) + timedelta(days=1)).isoformat()),
        task("whatsapp", task_id="no-consent", consent_whatsapp=False),
        task(task_id="maxed", attempts=3),
    ]
    result = await supplied_runtime.agents.get("followup").run(
        {"tasks": tasks, "dispatch": True}, ctx
    )
    assert result.status == "escalated" and result.output.actions == []
    assert {t.task_id for t in result.output.skipped} == {
        "closed",
        "replied",
        "future",
        "no-consent",
    }
    assert [t.task_id for t in result.output.escalations] == ["maxed"]
    assert await supplied_runtime.approvals.list_pending(ctx.tenant_id) == []


@pytest.mark.parametrize("dispatch", [False, True])
async def test_ungrounded_task_does_not_block_a_grounded_task(supplied_runtime, ctx, dispatch):
    add(supplied_runtime, ctx)
    tasks = [
        task(task_id="missing-query", knowledge_query=None),
        task(task_id="unsupported-question", knowledge_query="quasar telescope calibration"),
        task(task_id="grounded"),
    ]
    result = await supplied_runtime.agents.get("followup").run(
        {"tasks": tasks, "dispatch": dispatch}, ctx
    )
    assert result.status == ("pending_approval" if dispatch else "escalated")
    assert [a.task_id for a in result.output.actions] == ["grounded"]
    assert {e.task_id for e in result.output.escalations} == {
        "missing-query",
        "unsupported-question",
    }
    assert len(await supplied_runtime.approvals.list_pending(ctx.tenant_id)) == int(dispatch)
