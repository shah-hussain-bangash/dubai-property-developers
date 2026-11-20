from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import ClassVar

from agents.base.agent import AgentSpec, BaseAgent
from agents.base.context import ExecutionContext
from agents.marketing.schemas import CampaignDraft, MarketingInput, MarketingOutput
from schemas.agents.models import ImplementationStatus
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
        allowed_tools=frozenset(),
        status_notes="Rule-based segmentation and template copy; no campaign sending.",
    )
    input_model = MarketingInput
    output_model = MarketingOutput

    async def execute(self, data: MarketingInput, ctx: ExecutionContext) -> MarketingOutput:
        consented = [lead for lead in data.leads if lead.consent_marketing]
        segments: dict[str, list[str]] = defaultdict(list)
        for lead in consented:
            segments[segment_key(lead)].append(lead.lead_id)
        drafts = [
            CampaignDraft(
                segment=seg,
                audience_size=len(ids),
                headline=f"New options for {seg.split(':')[0].replace('_', ' ')} buyers",
                body=(
                    "We have curated options that may match your requirements. Reply to arrange a "
                    "call with a licensed advisor. Prices and availability are subject to confirmation."
                ),
            )
            for seg, ids in sorted(segments.items())
        ]
        recommendations = []
        if len(consented) < len(data.leads):
            recommendations.append(
                "Collect marketing consent at intake; non-consented leads were excluded."
            )
        largest = max(segments.items(), key=lambda kv: len(kv[1]), default=None)
        if largest:
            recommendations.append(f"Largest segment is '{largest[0]}' ({len(largest[1])} leads).")
        return MarketingOutput(
            segments=dict(segments),
            drafts=drafts,
            excluded_without_consent=len(data.leads) - len(consented),
            recommendations=recommendations,
        )
