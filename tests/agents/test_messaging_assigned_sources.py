"""Email and WhatsApp customer copy must use their own approved sources."""

from datetime import UTC, date, datetime, timedelta

import pytest

from workflows.runtime import build_runtime

TEXT = "Fictional garden policy includes eight gardens."


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


def email_request(**overrides):
    return {
        "template": "lead_acknowledgement",
        "knowledge_query": "garden policy",
        **overrides,
    }


def whatsapp_request(**overrides):
    return {
        "conversation_id": "fictional-wa-source-check",
        "from_e164": "+971500000001",
        "text": "What is the garden policy?",
        "received_at": datetime.now(UTC).isoformat(),
        "consent_whatsapp": True,
        "draft_reply": "Unverified guaranteed return of 99 percent.",
        "send_reply": True,
        **overrides,
    }


def add(runtime, ctx, agent, source="approved"):
    if source == "missing":
        return None
    return runtime.assigned_sources.add(
        "other-tenant" if source == "other-tenant" else ctx.tenant_id,
        "documents" if source == "other-agent" else agent,
        "Reviewed garden policy",
        "text",
        ["Fictional telescope maintenance manual." if source == "unrelated" else TEXT],
        customer_safe=source != "staff",
    )


@pytest.mark.parametrize("agent", ["email", "whatsapp"])
@pytest.mark.parametrize("source", ["missing", "staff", "other-agent", "other-tenant", "unrelated"])
async def test_messaging_refuses_unapproved_or_foreign_copy(supplied_runtime, ctx, agent, source):
    add(supplied_runtime, ctx, agent, source)
    payload = email_request(mode="send", recipient_email="fixture@example.com")
    if agent == "whatsapp":
        payload = whatsapp_request()
    result = await supplied_runtime.agents.get(agent).run(payload, ctx)
    assert result.status == "escalated"
    assert result.output.citations == [] and result.output.send_status is None
    assert result.output.approval_id is None
    if agent == "email":
        assert result.output.body is None and result.output.subject is None
    else:
        assert result.output.reply_text is None and result.output.template_name is None
        assert result.output.reply_mode == "no_reply"
    assert supplied_runtime.email_sender.outbox == []
    assert await supplied_runtime.approvals.list_pending(ctx.tenant_id) == []


async def test_email_quotes_own_sources_and_keeps_send_approval(supplied_runtime, ctx):
    source = add(supplied_runtime, ctx, "email")
    agent = supplied_runtime.agents.get("email")
    result = await agent.run(email_request(), ctx)
    assert result.status == "succeeded"
    assert result.output.body == TEXT and result.output.subject == "Reviewed garden policy"
    assert [c.excerpt for c in result.output.citations] == [TEXT]
    assert result.output.citations[0].document_id == f"{ctx.tenant_id}:{source['id']}"
    send = await agent.run(email_request(mode="send", recipient_email="fixture@example.com"), ctx)
    assert send.status == "pending_approval" and send.output.approval_id
    assert supplied_runtime.email_sender.outbox == []
    supplied_runtime.assigned_sources.remove(ctx.tenant_id, "email", source["id"])
    repeated = await agent.run(email_request(), ctx)
    assert repeated.status == "escalated" and repeated.output.body is None


async def test_email_needs_a_knowledge_query_but_classification_still_works(supplied_runtime, ctx):
    add(supplied_runtime, ctx, "email")
    agent = supplied_runtime.agents.get("email")
    draft = await agent.run({"template": "lead_acknowledgement"}, ctx)
    assert draft.status == "escalated" and draft.output.body is None
    classified = await agent.run({"mode": "classify", "inbound_text": "Please unsubscribe"}, ctx)
    assert classified.status == "succeeded" and classified.output.classification == "unsubscribe"
    assert classified.output.body is None


async def test_whatsapp_ignores_unverified_draft_and_quotes_own_source(supplied_runtime, ctx):
    source = add(supplied_runtime, ctx, "whatsapp")
    result = await supplied_runtime.agents.get("whatsapp").run(whatsapp_request(), ctx)
    assert result.status == "pending_approval" and result.output.approval_id
    assert result.output.reply_text == TEXT and result.output.reply_mode == "free_text"
    assert [c.excerpt for c in result.output.citations] == [TEXT]
    assert result.output.citations[0].document_id == f"{ctx.tenant_id}:{source['id']}"
    assert supplied_runtime.email_sender.outbox == []
    supplied_runtime.assigned_sources.remove(ctx.tenant_id, "whatsapp", source["id"])
    repeated = await supplied_runtime.agents.get("whatsapp").run(whatsapp_request(), ctx)
    assert repeated.status == "escalated" and repeated.output.reply_text is None


async def test_whatsapp_outside_window_has_no_unverified_template_fallback(supplied_runtime, ctx):
    add(supplied_runtime, ctx, "whatsapp")
    result = await supplied_runtime.agents.get("whatsapp").run(
        whatsapp_request(received_at=(datetime.now(UTC) - timedelta(days=2)).isoformat()), ctx
    )
    assert result.status == "escalated"
    assert result.output.reply_mode == "no_reply"
    assert result.output.template_name is None and result.output.reply_text is None
    assert result.output.approval_id is None


@pytest.mark.parametrize("opt_out", [False, True])
async def test_whatsapp_sources_cannot_override_consent_or_opt_out(supplied_runtime, ctx, opt_out):
    add(supplied_runtime, ctx, "whatsapp")
    payload = whatsapp_request(consent_whatsapp=opt_out)
    if opt_out:
        payload["text"] = "STOP sending, unsubscribe"
    result = await supplied_runtime.agents.get("whatsapp").run(payload, ctx)
    assert result.status == "escalated" and result.output.reply_mode == "no_reply"
    assert result.output.reply_text is None and result.output.approval_id is None


async def test_email_sources_cannot_override_marketing_consent(supplied_runtime, ctx):
    add(supplied_runtime, ctx, "email")
    result = await supplied_runtime.agents.get("email").run(
        email_request(
            mode="send",
            recipient_email="fixture@example.com",
            is_marketing=True,
            consent_marketing=False,
        ),
        ctx,
    )
    assert result.status == "failed" and result.error.code == "policy_violation"
    assert await supplied_runtime.approvals.list_pending(ctx.tenant_id) == []


async def test_whatsapp_complaint_requires_staff_even_with_approved_sources(supplied_runtime, ctx):
    add(supplied_runtime, ctx, "whatsapp")
    result = await supplied_runtime.agents.get("whatsapp").run(
        whatsapp_request(text="I have a complaint about the garden policy"), ctx
    )
    assert result.status == "escalated" and result.output.reply_mode == "no_reply"
    assert result.output.reply_text is None and result.output.approval_id is None


@pytest.mark.parametrize("agent", ["email", "whatsapp"])
async def test_expired_sources_cannot_supply_a_message(supplied_runtime, ctx, monkeypatch, agent):
    review = date.today() + timedelta(days=1)
    supplied_runtime.assigned_sources.add(
        ctx.tenant_id,
        agent,
        "Review fixture",
        "text",
        [TEXT],
        review_by=review,
        customer_safe=True,
    )

    class Later(date):
        @classmethod
        def today(cls):
            return review + timedelta(days=1)

    monkeypatch.setattr("knowledge.assigned_sources.date", Later)
    payload = email_request() if agent == "email" else whatsapp_request()
    result = await supplied_runtime.agents.get(agent).run(payload, ctx)
    assert result.status == "escalated" and result.output.citations == []
    assert result.output.approval_id is None
