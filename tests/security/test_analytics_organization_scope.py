"""Analytics only reports owned records and accepts owned lead inputs."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from agents.base.context import InMemoryExecutionRecorder
from core.exceptions.errors import AuthorizationError, DomainValidationError
from knowledge.agent_data.catalogue import dataset_ids
from tests.factories import normalized_lead
from tools.base import ToolCallContext


@pytest.mark.parametrize("agent_id", dataset_ids())
async def test_mismatched_agent_context_fails_before_execution(runtime, ctx, monkeypatch, agent_id):
    agent = runtime.agents.get(agent_id)
    execute = AsyncMock()
    monkeypatch.setattr(agent, "execute", execute)
    result = await agent.run({}, replace(ctx, tenant_id="other-org"))
    assert result.status == "failed" and result.error.code == "forbidden"
    execute.assert_not_awaited()
    record = runtime.deps.executions.records[-1]
    assert record["tenant_id"] == ctx.principal.tenant_id


@pytest.mark.parametrize("outcome", ["success", "invalid", "disabled", "failure", "timeout"])
async def test_every_record_path_uses_trusted_organization(runtime, ctx, monkeypatch, outcome):
    agent = runtime.agents.get("supervisor")
    payload = {"request_type": "analytics", "payload": {"tenant_id": "other-org"}}
    if outcome == "invalid":
        payload = {}
    elif outcome == "disabled":
        agent.config.enabled = False
    elif outcome == "failure":
        monkeypatch.setattr(
            agent,
            "execute",
            AsyncMock(side_effect=DomainValidationError("Fictional validation failure")),
        )
    elif outcome == "timeout":

        async def wait():
            await asyncio.Event().wait()

        monkeypatch.setattr(agent, "execute", lambda *_: wait())
        agent.config.timeout_seconds = 0.005
    result = await agent.run(payload, ctx)
    expected = {
        "success": "succeeded",
        "invalid": "failed",
        "disabled": "failed",
        "failure": "failed",
        "timeout": "timed_out",
    }
    assert result.status == expected[outcome]
    record = runtime.deps.executions.records[-1]
    assert record["tenant_id"] == ctx.tenant_id
    assert record["status"] == result.status


async def test_agent_performance_excludes_foreign_and_unowned_records(runtime, ctx):
    other = replace(
        ctx, tenant_id="other-org", principal=replace(ctx.principal, tenant_id="other-org")
    )
    for owner in [ctx, other, other]:
        await runtime.agents.get("supervisor").run({"request_type": "analytics"}, owner)
    await runtime.deps.executions.record(
        {
            "agent_id": "fictional-legacy-agent",
            "status": "succeeded",
            "duration_ms": 1,
        }
    )
    result = await runtime.agents.get("analytics").run({"leads": []}, ctx)
    assert result.status == "succeeded"
    assert [(p.agent_id, p.runs) for p in result.output.agent_performance] == [("supervisor", 1)]
    foreign = await runtime.agents.get("analytics").run({"leads": []}, other)
    assert [(p.agent_id, p.runs) for p in foreign.output.agent_performance] == [("supervisor", 2)]


@pytest.mark.parametrize("mixed", [False, True])
async def test_analytics_agent_rejects_foreign_lead_input(runtime, ctx, mixed):
    leads = [normalized_lead(tenant_id="other-org")]
    if mixed:
        leads.append(normalized_lead())
    result = await runtime.agents.get("analytics").run(
        {"leads": [lead.model_dump(mode="json") for lead in leads]}, ctx
    )
    assert result.status == "failed" and result.error.code == "forbidden"
    assert result.output is None


async def test_direct_contextual_summary_checks_principal_and_lead_ownership(runtime, ctx):
    tool = runtime.tools.get("analytics.sales_summary")
    own = ToolCallContext(ctx.principal, ctx.tenant_id, "fictional-analytics-scope")
    for call, tenant in [(own, "other-org"), (replace(own, tenant_id="other-org"), "other-org")]:
        with pytest.raises(AuthorizationError):
            await tool.execute_with_context(
                {"leads": [normalized_lead(tenant_id=tenant).model_dump(mode="json")]}, call
            )


async def test_own_report_preserves_counts_and_optional_performance(runtime, ctx):
    result = await runtime.agents.get("analytics").run(
        {
            "leads": [
                normalized_lead(status="converted").model_dump(mode="json"),
                normalized_lead(lead_id="fictional-second-lead").model_dump(mode="json"),
            ],
            "include_agent_performance": False,
        },
        ctx,
    )
    assert result.status == "succeeded"
    assert result.output.sales["total_leads"] == 2
    assert result.output.sales["conversion_rate"] == 0.5
    assert result.output.agent_performance == []


@pytest.mark.parametrize("mutation", ["input", "output", "scoped-output"])
async def test_record_snapshots_cannot_reassign_organization(mutation):
    recorder = InMemoryExecutionRecorder()
    record = {
        "tenant_id": "owner-org",
        "agent_id": "supervisor",
        "status": "succeeded",
        "duration_ms": 1,
        "details": {"marker": "original"},
    }
    await recorder.record(record)
    target = (
        record
        if mutation == "input"
        else recorder.records[0]
        if mutation == "output"
        else recorder.records_for_tenant("owner-org")[0]
    )
    target["tenant_id"] = "other-org"
    target["details"]["marker"] = "changed"
    assert recorder.records[0]["tenant_id"] == "owner-org"
    assert recorder.records[0]["details"] == {"marker": "original"}
