"""A human approval cannot revive withdrawn knowledge or authorize altered source copy."""

from datetime import UTC, date, datetime, timedelta

import pytest

from core.exceptions.errors import AuthorizationError, PolicyViolationError
from tools.base import ToolCallContext
from workflows.runtime import build_runtime

TEXT = "Fictional garden policy includes eight gardens."
SENDERS = ["email", "whatsapp", "followup-email", "followup-whatsapp"]


@pytest.fixture
async def supplied_runtime(settings, tmp_path):
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    runtime = build_runtime(settings)
    await runtime.initialize()
    try:
        yield runtime
    finally:
        await runtime.shutdown()


async def queue(runtime, ctx, sender):
    agent = "followup" if sender.startswith("followup-") else sender
    review = date.today() + timedelta(days=1)
    source = runtime.assigned_sources.add(
        ctx.tenant_id,
        agent,
        "Reviewed garden policy",
        "text",
        [TEXT],
        review_by=review,
        customer_safe=True,
    )
    now = datetime.now(UTC)
    if sender == "email":
        payload = {
            "mode": "send",
            "knowledge_query": "garden policy",
            "recipient_email": "fixture@example.com",
        }
    elif sender == "whatsapp":
        payload = {
            "conversation_id": "fictional-approval",
            "from_e164": "+971500000001",
            "text": "What is the garden policy?",
            "received_at": now.isoformat(),
            "consent_whatsapp": True,
            "send_reply": True,
        }
    else:
        payload = {
            "dispatch": True,
            "tasks": [
                {
                    "task_id": "fictional-approval-task",
                    "lead_id": "fictional-lead",
                    "contact_first_name": "Fictional Visitor",
                    "channel": sender.split("-", 1)[1],
                    "due_at": (now - timedelta(hours=1)).isoformat(),
                    "email": "fixture@example.com",
                    "to_e164": "+971500000001",
                    "consent_whatsapp": True,
                    "last_inbound_at": now.isoformat(),
                    "knowledge_query": "garden policy",
                }
            ],
        }
    result = await runtime.agents.get(agent).run(payload, ctx)
    assert result.status == "pending_approval"
    approval = (
        result.output.actions[0].approval_id if agent == "followup" else result.output.approval_id
    )
    assert (await runtime.approvals.get(approval)).requested_by_agent == agent
    return agent, source, review, approval


@pytest.mark.parametrize("sender", SENDERS)
@pytest.mark.parametrize("withdrawal", ["remove", "unapprove", "expire", "retitle"])
async def test_withdrawn_source_blocks_approved_execution(
    supplied_runtime, ctx, monkeypatch, sender, withdrawal
):
    agent, source, review, approval = await queue(supplied_runtime, ctx, sender)
    if withdrawal == "remove":
        supplied_runtime.assigned_sources.remove(ctx.tenant_id, agent, source["id"])
    elif withdrawal == "expire":

        class Later(date):
            @classmethod
            def today(cls):
                return review + timedelta(days=1)

        monkeypatch.setattr("knowledge.assigned_sources.date", Later)
    else:
        supplied_runtime.assigned_sources.add(
            ctx.tenant_id,
            agent,
            "Revised garden policy title" if withdrawal == "retitle" else "Reviewed garden policy",
            "text",
            [TEXT],
            review_by=review,
            customer_safe=withdrawal != "unapprove",
        )
    await supplied_runtime.approvals.decide(
        approval, approved=True, decided_by=ctx.principal.subject
    )
    with pytest.raises(PolicyViolationError):
        await supplied_runtime.gateway.execute_approved(approval, ctx.principal)
    assert supplied_runtime.email_sender.outbox == []
    assert supplied_runtime.integrations.whatsapp.outbox == []


@pytest.mark.parametrize("sender", SENDERS)
async def test_current_approved_sources_execute_once_and_replay_without_resending(
    supplied_runtime, ctx, sender
):
    agent, source, _, approval = await queue(supplied_runtime, ctx, sender)
    await supplied_runtime.approvals.decide(
        approval, approved=True, decided_by=ctx.principal.subject
    )
    result = await supplied_runtime.gateway.execute_approved(approval, ctx.principal)
    assert result.status == "executed"
    supplied_runtime.assigned_sources.remove(ctx.tenant_id, agent, source["id"])
    replay = await supplied_runtime.gateway.execute_approved(approval, ctx.principal)
    assert replay.status == "replayed"
    sent = supplied_runtime.email_sender.outbox + supplied_runtime.integrations.whatsapp.outbox
    assert len(sent) == 1 and sent[0]["body"] == TEXT
    assert "knowledge_citations" not in sent[0]


@pytest.mark.parametrize("tool", ["email.send", "whatsapp.send_message"])
@pytest.mark.parametrize(
    "tamper", ["missing", "body", "foreign-agent", "foreign-tenant", "excerpt"]
)
async def test_approved_arbitrary_payload_cannot_spoof_source_provenance(
    supplied_runtime, ctx, tool, tamper
):
    agent = "email" if tool == "email.send" else "whatsapp"
    owner = "documents" if tamper == "foreign-agent" else agent
    tenant = "other-tenant" if tamper == "foreign-tenant" else ctx.tenant_id
    supplied_runtime.assigned_sources.add(
        tenant, owner, "Reviewed garden policy", "text", [TEXT], customer_safe=True
    )
    citations = supplied_runtime.assigned_sources.tool_search(tenant, owner, "garden policy")[
        "citations"
    ]
    payload = {"knowledge_citations": citations}
    if tool == "email.send":
        payload.update(to="fixture@example.com", subject="Reviewed garden policy", body=TEXT)
    else:
        payload.update(
            to_e164="+971500000001",
            consent_whatsapp=True,
            last_inbound_at=datetime.now(UTC).isoformat(),
            text=TEXT,
        )
    if tamper == "missing":
        payload.pop("knowledge_citations")
    if tamper == "body":
        payload["body" if tool == "email.send" else "text"] += " Unverified new claim."
    if tamper == "excerpt":
        payload["knowledge_citations"][0]["excerpt"] = "Unverified replacement excerpt."
        payload["body" if tool == "email.send" else "text"] = "Unverified replacement excerpt."
    requested = await supplied_runtime.agents.get(agent).use_tool(ctx, tool, payload)
    await supplied_runtime.approvals.decide(
        requested.approval_id, approved=True, decided_by=ctx.principal.subject
    )
    with pytest.raises(PolicyViolationError):
        await supplied_runtime.gateway.execute_approved(requested.approval_id, ctx.principal)
    assert supplied_runtime.email_sender.outbox == []
    assert supplied_runtime.integrations.whatsapp.outbox == []


@pytest.mark.parametrize("sender", ["email", "whatsapp"])
async def test_multiple_source_quotes_and_pdf_references_survive_approval(
    supplied_runtime, ctx, sender
):
    for kind, text in [
        ("pdf", "Fictional garden policy includes two car spaces."),
        ("text", "Fictional garden policy includes six lifts."),
    ]:
        supplied_runtime.assigned_sources.add(
            ctx.tenant_id, sender, "Reviewed " + kind, kind, [text], customer_safe=True
        )
    _, _, _, approval = await queue(supplied_runtime, ctx, sender)
    request = await supplied_runtime.approvals.get(approval)
    references = request.payload["knowledge_citations"]
    assert len(references) == 3 and any(":1:0" in c["chunk_id"] for c in references)
    await supplied_runtime.approvals.decide(
        approval, approved=True, decided_by=ctx.principal.subject
    )
    result = await supplied_runtime.gateway.execute_approved(approval, ctx.principal)
    assert result.status == "executed"
    sent = supplied_runtime.email_sender.outbox + supplied_runtime.integrations.whatsapp.outbox
    assert len(sent) == 1 and sent[0]["body"] == "\n\n".join(c["excerpt"] for c in references)


async def test_modified_email_subject_is_not_authorized_by_body_citations(supplied_runtime, ctx):
    await queue(supplied_runtime, ctx, "email")
    citations = supplied_runtime.assigned_sources.tool_search(
        ctx.tenant_id, "email", "garden policy"
    )["citations"]
    requested = await supplied_runtime.agents.get("email").use_tool(
        ctx,
        "email.send",
        {
            "to": "fixture@example.com",
            "subject": "Unverified subject promise",
            "body": TEXT,
            "knowledge_citations": citations,
        },
    )
    await supplied_runtime.approvals.decide(
        requested.approval_id, approved=True, decided_by=ctx.principal.subject
    )
    with pytest.raises(PolicyViolationError):
        await supplied_runtime.gateway.execute_approved(requested.approval_id, ctx.principal)
    assert supplied_runtime.email_sender.outbox == []


@pytest.mark.parametrize("tool", ["email.send", "whatsapp.send_message"])
@pytest.mark.parametrize("mode", ["direct", "no-agent"])
async def test_payload_cannot_supply_its_own_trusted_agent_identity(
    supplied_runtime, ctx, tool, mode
):
    agent = "email" if tool == "email.send" else "whatsapp"
    await queue(supplied_runtime, ctx, agent)
    payload = {
        "agent_id": agent,
        "knowledge_citations": supplied_runtime.assigned_sources.tool_search(
            ctx.tenant_id, agent, "garden policy"
        )["citations"],
    }
    if tool == "email.send":
        payload.update(to="fixture@example.com", subject="Reviewed garden policy", body=TEXT)
    else:
        payload.update(
            to_e164="+971500000001",
            consent_whatsapp=True,
            last_inbound_at=datetime.now(UTC).isoformat(),
            text=TEXT,
        )
    if mode == "direct":
        with pytest.raises(AuthorizationError):
            await supplied_runtime.tools.get(tool).execute(payload)
    else:
        unscoped = ToolCallContext(
            principal=ctx.principal, tenant_id=ctx.tenant_id, correlation_id="fictional-unscoped"
        )
        requested = await supplied_runtime.gateway.invoke(unscoped, tool, payload)
        await supplied_runtime.approvals.decide(
            requested.approval_id, approved=True, decided_by=ctx.principal.subject
        )
        with pytest.raises(PolicyViolationError):
            await supplied_runtime.gateway.execute_approved(requested.approval_id, ctx.principal)
    assert supplied_runtime.email_sender.outbox == []
    assert supplied_runtime.integrations.whatsapp.outbox == []
