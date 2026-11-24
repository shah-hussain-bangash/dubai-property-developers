"""Source-only summaries cannot echo unassigned caller text or another owner's facts."""

from datetime import date, timedelta

import pytest

from workflows.runtime import build_runtime

TEXT = "Fictional garden policy includes eight gardens. Garden access requires a booking."
UNASSIGNED = "Unverified broker promise guarantees a return of 99 percent."


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


def add(runtime, ctx, source="approved"):
    if source == "missing":
        return None
    return runtime.assigned_sources.add(
        "other-tenant" if source == "other-tenant" else ctx.tenant_id,
        "email" if source == "other-agent" else "documents",
        "Reviewed garden policy",
        "text",
        ["Fictional telescope calibration manual." if source == "unrelated" else TEXT],
        review_by=date.today() + timedelta(days=1) if source == "expired" else None,
        customer_safe=source != "staff",
    )


def request(**overrides):
    return {"action": "summarize", "query": "garden policy", "text": UNASSIGNED, **overrides}


@pytest.mark.parametrize(
    "source", ["missing", "staff", "other-agent", "other-tenant", "unrelated", "expired"]
)
async def test_unavailable_summary_sources_never_fall_back_to_caller_text(
    supplied_runtime, ctx, monkeypatch, source
):
    add(supplied_runtime, ctx, source)
    if source == "expired":
        later = date.today() + timedelta(days=2)

        class Later(date):
            @classmethod
            def today(cls):
                return later

        monkeypatch.setattr("knowledge.assigned_sources.date", Later)
    result = await supplied_runtime.agents.get("documents").run(request(), ctx)
    assert result.status == "escalated"
    assert result.output.summary is None and result.output.answer is None
    assert result.output.citations == [] and result.output.needs_human


async def test_summary_requires_query_even_when_unassigned_text_is_provided(supplied_runtime, ctx):
    add(supplied_runtime, ctx)
    result = await supplied_runtime.agents.get("documents").run(request(query=None), ctx)
    assert result.status == "escalated"
    assert result.output.summary is None and result.output.citations == []


@pytest.mark.parametrize("sentences", [1, 3])
async def test_summary_quotes_own_approved_passages_and_retains_citations(
    supplied_runtime, ctx, sentences
):
    source = add(supplied_runtime, ctx)
    agent = supplied_runtime.agents.get("documents")
    result = await agent.run(request(max_sentences=sentences), ctx)
    assert result.status == "succeeded" and not result.output.needs_human
    summary = result.output.summary
    if sentences == 1:
        assert summary in [
            "Fictional garden policy includes eight gardens.",
            "Garden access requires a booking.",
        ]
    else:
        assert summary == TEXT
    assert "99 percent" not in summary
    assert [c.excerpt for c in result.output.citations] == [TEXT]
    assert result.output.citations[0].document_id == f"{ctx.tenant_id}:{source['id']}"
    assert result.output.answer is None and result.output.confidence > 0
    supplied_runtime.assigned_sources.remove(ctx.tenant_id, "documents", source["id"])
    repeated = await agent.run(request(), ctx)
    assert repeated.status == "escalated" and repeated.output.summary is None


async def test_staff_summary_uses_own_staff_source_without_customer_approval(supplied_runtime, ctx):
    add(supplied_runtime, ctx, "staff")
    result = await supplied_runtime.agents.get("documents").run(request(audience="staff"), ctx)
    assert result.status == "succeeded" and result.output.summary == TEXT
    assert result.output.citations


async def test_summary_retains_pdf_passage_reference(supplied_runtime, ctx):
    source = supplied_runtime.assigned_sources.add(
        ctx.tenant_id, "documents", "Fictional PDF", "pdf", [TEXT], customer_safe=True
    )
    result = await supplied_runtime.agents.get("documents").run(
        {"action": "summarize", "query": "garden policy"}, ctx
    )
    assert result.status == "succeeded" and result.output.summary == TEXT
    assert result.output.citations[0].chunk_id == f"{source['id']}:1:0"
