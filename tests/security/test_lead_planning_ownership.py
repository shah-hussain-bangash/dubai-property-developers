"""Campaign and qualification plans must not blend organizations' lead inputs."""

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from agents.marketing.schemas import MarketingInput
from core.exceptions.errors import AuthorizationError
from tests.factories import normalized_lead
from tools.analytics.tools import LeadScoringTool
from tools.base import ToolCallContext, ToolResult
from workflows.runtime import build_runtime

TEXT = "Fictional garden policy allows two visits."


@pytest.fixture(params=[False, True], ids=["fixture-mode", "source-only"])
async def planning_runtime(request, settings, tmp_path, ctx):
    if request.param:
        settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    runtime = build_runtime(settings)
    await runtime.initialize()
    if runtime.assigned_sources is not None:
        runtime.assigned_sources.add(
            ctx.tenant_id,
            "marketing",
            "Fictional garden policy",
            "text",
            [TEXT],
            customer_safe=True,
        )
    try:
        yield runtime
    finally:
        await runtime.shutdown()


@pytest.mark.parametrize("mixed", [False, True])
@pytest.mark.parametrize("consented", [False, True])
async def test_foreign_campaign_inputs_fail_before_any_source_lookup(
    planning_runtime, ctx, monkeypatch, mixed, consented
):
    lookup = AsyncMock(
        return_value=ToolResult(tool="documents.search", status="executed", data={"citations": []})
    )
    monkeypatch.setattr(planning_runtime.gateway, "invoke", lookup)
    leads = [normalized_lead(tenant_id="other-org", consent_marketing=consented)]
    if mixed:
        leads.append(normalized_lead(lead_id="fictional-own-lead", consent_marketing=True))
    result = await planning_runtime.agents.get("marketing").run(
        {
            "leads": [lead.model_dump(mode="json") for lead in leads],
            "campaign_goal": "garden policy",
        },
        ctx,
    )
    assert result.status == "failed" and result.error.code == "forbidden"
    assert result.output is None
    lookup.assert_not_awaited()


async def test_foreign_qualification_input_is_rejected(planning_runtime, ctx):
    result = await planning_runtime.agents.get("qualification").run(
        {"lead": normalized_lead(tenant_id="other-org").model_dump(mode="json")}, ctx
    )
    assert result.status == "failed" and result.error.code == "forbidden"
    assert result.output is None


async def test_own_campaign_keeps_consent_filter_and_own_qualification(planning_runtime, ctx):
    consented = normalized_lead(lead_id="fictional-own-consented", consent_marketing=True)
    excluded = normalized_lead(lead_id="fictional-own-without-consent", consent_marketing=False)
    campaign = await planning_runtime.agents.get("marketing").run(
        {
            "leads": [consented.model_dump(mode="json"), excluded.model_dump(mode="json")],
            "campaign_goal": "garden policy",
        },
        ctx,
    )
    assert campaign.status == "succeeded"
    assert [lead_id for ids in campaign.output.segments.values() for lead_id in ids] == [
        consented.lead_id
    ]
    assert campaign.output.excluded_without_consent == 1
    assert len(campaign.output.drafts) == 1
    if planning_runtime.assigned_sources is not None:
        assert campaign.output.drafts[0].body == TEXT
        assert campaign.output.drafts[0].citations
    qualification = await planning_runtime.agents.get("qualification").run(
        {"lead": consented.model_dump(mode="json")}, ctx
    )
    assert qualification.status == "succeeded"
    assert qualification.output.lead_id == consented.lead_id
    assert 0 <= qualification.output.score.score <= 100


@pytest.mark.parametrize("mismatch", ["lead", "principal"])
async def test_contextual_scoring_checks_owner_identity(manager, mismatch):
    ctx = ToolCallContext(manager, manager.tenant_id, "fictional-scoring-owner")
    lead = normalized_lead(tenant_id="other-org" if mismatch == "lead" else manager.tenant_id)
    if mismatch == "principal":
        ctx = replace(ctx, principal=replace(manager, tenant_id="other-org"))
    with pytest.raises(AuthorizationError):
        await LeadScoringTool().execute_with_context({"lead": lead.model_dump(mode="json")}, ctx)


async def test_direct_campaign_execution_checks_principal_identity(runtime, ctx):
    forged = replace(ctx, principal=replace(ctx.principal, tenant_id="other-org"))
    data = MarketingInput(leads=[normalized_lead(consent_marketing=True)])
    with pytest.raises(AuthorizationError):
        await runtime.agents.get("marketing").execute(data, forged)


async def test_standalone_scoring_remains_a_pure_supplied_data_calculation():
    tool = LeadScoringTool()
    own = normalized_lead()
    other = own.model_copy(update={"tenant_id": "other-org"})
    assert await tool.execute({"lead": own.model_dump(mode="json")}) == await tool.execute(
        {"lead": other.model_dump(mode="json")}
    )
