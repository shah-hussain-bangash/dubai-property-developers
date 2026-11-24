"""Marketing copy cannot fall back to invented template facts in supplied mode."""

import pytest

from tests.factories import normalized_lead
from workflows.runtime import build_runtime


@pytest.fixture
async def supplied_runtime(settings, tmp_path):
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    runtime = build_runtime(settings)
    await runtime.initialize()
    try:
        yield runtime
    finally:
        await runtime.shutdown()


def campaign(consent=True):
    return {
        "leads": [normalized_lead(consent_marketing=consent).model_dump(mode="json")],
        "campaign_goal": "garden campaign",
    }


@pytest.mark.parametrize("source", ["missing", "staff", "other-agent", "other-tenant", "unrelated"])
async def test_unapproved_or_foreign_sources_cannot_supply_marketing_copy(
    supplied_runtime, ctx, source
):
    if source != "missing":
        supplied_runtime.assigned_sources.add(
            "other-tenant" if source == "other-tenant" else ctx.tenant_id,
            "documents" if source == "other-agent" else "marketing",
            "Fictional garden campaign",
            "text",
            [
                "Fictional telescope calibration manual."
                if source == "unrelated"
                else "Fictional garden campaign includes eight gardens."
            ],
            customer_safe=source != "staff",
        )
    result = await supplied_runtime.agents.get("marketing").run(campaign(), ctx)
    assert result.status == "escalated"
    assert result.output.drafts == []
    assert result.output.needs_human is True
    assert supplied_runtime.email_sender.outbox == []


async def test_approved_own_source_is_quoted_and_cited_without_template_claims(
    supplied_runtime, ctx
):
    text = "Fictional garden campaign includes eight gardens."
    source = supplied_runtime.assigned_sources.add(
        ctx.tenant_id,
        "marketing",
        "Reviewed garden campaign",
        "text",
        [text],
        customer_safe=True,
    )
    result = await supplied_runtime.agents.get("marketing").run(campaign(), ctx)
    assert result.status == "succeeded"
    draft = result.output.drafts[0]
    assert draft.headline == "Reviewed garden campaign"
    assert draft.body == text
    assert draft.status == "draft_requires_approval"
    assert supplied_runtime.agents.get("marketing").spec.allowed_tools == {"documents.search"}
    assert [c.excerpt for c in draft.citations] == [text]
    assert draft.citations[0].document_id == f"{ctx.tenant_id}:{source['id']}"
    assert result.output.excluded_without_consent == 0
    assert supplied_runtime.email_sender.outbox == []

    supplied_runtime.assigned_sources.remove(ctx.tenant_id, "marketing", source["id"])
    repeated = await supplied_runtime.agents.get("marketing").run(campaign(), ctx)
    assert repeated.status == "escalated" and repeated.output.drafts == []


async def test_missing_knowledge_does_not_override_marketing_consent(supplied_runtime, ctx):
    result = await supplied_runtime.agents.get("marketing").run(campaign(consent=False), ctx)
    assert result.status == "succeeded"
    assert result.output.segments == {} and result.output.drafts == []
    assert result.output.excluded_without_consent == 1
    assert supplied_runtime.email_sender.outbox == []
