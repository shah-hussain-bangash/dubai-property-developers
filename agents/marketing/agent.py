from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import ClassVar

from agents.base.agent import AgentSpec, BaseAgent
from agents.base.context import ExecutionContext
from agents.marketing.schemas import CampaignDraft, MarketingInput, MarketingOutput
from knowledge.assigned_sources import NO_ANSWER
from schemas.agents.models import AgentRunStatus, ImplementationStatus
from schemas.conversations.models import Citation
from schemas.leads.models import NormalizedLead


def _budget_band(lead: NormalizedLead) -> str:
    budget = lead.budget_max_aed
    if budget is None:
        return "budget-unknown"
    if budget < Decimal(1_000_000):
        return "under-1m"
    if budget < Decimal(3_000_000):
        return "1m-3m"
    return "3m-plus"


def segment_key(lead: NormalizedLead) -> str:
    return f"{lead.purpose.value}:{_budget_band(lead)}"


class MarketingAgent(BaseAgent[MarketingInput, MarketingOutput]):
    spec: ClassVar[AgentSpec] = AgentSpec(
        agent_id="marketing",
        name="Marketing Agent",
        description="Segments consented leads and prepares campaign copy drafts for review.",
        responsibilities=[
            "Support lead segmentation",
            "Prepare campaign copy drafts",
            "Identify campaign opportunities",
            "Prepare analytics-driven recommendations",
        ],
        implementation_status=ImplementationStatus.PARTIAL,
        allowed_tools=frozenset({"documents.search"}),
        status_notes="Rule-based segmentation; supplied-source copy quotes approved own sources. "
        "Drafts need review; no campaign sending.",
    )
    input_model = MarketingInput
    output_model = MarketingOutput

    async def execute(self, data: MarketingInput, ctx: ExecutionContext) -> MarketingOutput:
        consented = [lead for lead in data.leads if lead.consent_marketing]
        segments: dict[str, list[str]] = defaultdict(list)
        for lead in consented:
            segments[segment_key(lead)].append(lead.lead_id)
        citations: list[Citation] = []
        if self.deps.supplied_knowledge_only and segments:
            result = await self.use_tool(
                ctx,
                "documents.search",
                {
                    "query": data.campaign_goal,
                    "tenant_id": ctx.tenant_id,
                    "audience": "customer",
                    "k": 3,
                },
            )
            if not result.data.get("has_stale"):
                citations = [Citation.model_validate(c) for c in result.data.get("citations", [])]
        needs_human = self.deps.supplied_knowledge_only and bool(segments) and not citations
        drafts = [
            CampaignDraft(
                segment=seg,
                audience_size=len(ids),
                headline=citations[0].title
                if self.deps.supplied_knowledge_only
                else f"New options for {seg.split(':')[0].replace('_', ' ')} buyers",
                body="\n\n".join(c.excerpt for c in citations)
                if self.deps.supplied_knowledge_only
                else (
                    "We have curated options that may match your requirements. Reply to arrange a "
                    "call with a licensed advisor. Prices and availability are subject to confirmation."
                ),
                citations=citations,
            )
            for seg, ids in sorted(segments.items())
            if not needs_human
        ]
        recommendations = []
        if len(consented) < len(data.leads):
            recommendations.append(
                "Collect marketing consent at intake; non-consented leads were excluded."
            )
        largest = max(segments.items(), key=lambda kv: len(kv[1]), default=None)
        if largest:
            recommendations.append(f"Largest segment is '{largest[0]}' ({len(largest[1])} leads).")
        if needs_human:
            recommendations.append(NO_ANSWER)
        return MarketingOutput(
            segments=dict(segments),
            drafts=drafts,
            excluded_without_consent=len(data.leads) - len(consented),
            recommendations=recommendations,
            needs_human=needs_human,
        )

    def outcome_status(self, output: MarketingOutput) -> AgentRunStatus:
        return AgentRunStatus.ESCALATED if output.needs_human else AgentRunStatus.SUCCEEDED
