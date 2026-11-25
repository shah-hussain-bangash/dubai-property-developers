from __future__ import annotations

from collections import defaultdict
from typing import Any, ClassVar

from agents.analytics.schemas import AgentPerformance, AnalyticsInput, AnalyticsOutput
from agents.base.agent import AgentSpec, BaseAgent
from agents.base.context import ExecutionContext, InMemoryExecutionRecorder
from schemas.agents.models import ImplementationStatus

_OK = {"succeeded", "pending_approval", "escalated"}


def summarize_executions(records: list[dict[str, Any]]) -> list[AgentPerformance]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["agent_id"]].append(record)
    return [
        AgentPerformance(
            agent_id=agent_id,
            runs=len(rows),
            success_rate=round(sum(r["status"] in _OK for r in rows) / len(rows), 4),
            avg_duration_ms=round(sum(r["duration_ms"] for r in rows) / len(rows), 2),
        )
        for agent_id, rows in sorted(grouped.items())
    ]


class AnalyticsAgent(BaseAgent[AnalyticsInput, AnalyticsOutput]):
    spec: ClassVar[AgentSpec] = AgentSpec(
        agent_id="analytics",
        name="Analytics Agent",
        description="Reports lead sources, conversion and agent performance metrics.",
        responsibilities=[
            "Report lead sources",
            "Monitor conversion metrics",
            "Analyze agent performance",
            "Report workflow statistics",
        ],
        implementation_status=ImplementationStatus.PARTIAL,
        allowed_tools=frozenset({"analytics.sales_summary"}),
        status_notes="Aggregates in-memory data; SQL-backed reporting and CRM activity summaries pending.",
    )
    input_model = AnalyticsInput
    output_model = AnalyticsOutput

    async def execute(self, data: AnalyticsInput, ctx: ExecutionContext) -> AnalyticsOutput:
        sales = await self.use_tool(
            ctx,
            "analytics.sales_summary",
            {"leads": [lead.model_dump(mode="json") for lead in data.leads]},
        )
        performance: list[AgentPerformance] = []
        recorder = self.deps.executions
        if data.include_agent_performance and isinstance(recorder, InMemoryExecutionRecorder):
            performance = summarize_executions(recorder.records_for_tenant(ctx.tenant_id))
        return AnalyticsOutput(sales=sales.data, agent_performance=performance)
