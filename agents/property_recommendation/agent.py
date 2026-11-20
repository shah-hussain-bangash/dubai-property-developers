from __future__ import annotations

from typing import ClassVar

from agents.base.agent import AgentSpec, BaseAgent
from agents.base.context import ExecutionContext
from agents.property_recommendation.schemas import RecommendationInput, RecommendationOutput
from schemas.agents.models import ImplementationStatus
from schemas.properties.models import PropertyRecommendation


class PropertyRecommendationAgent(BaseAgent[RecommendationInput, RecommendationOutput]):
    spec: ClassVar[AgentSpec] = AgentSpec(
        agent_id="property_recommendation",
        name="Property Recommendation Agent",
        description="Matches customer requirements to eligible properties with explained rankings.",
        responsibilities=[
            "Filter properties by budget, location, type and availability",
            "Evaluate payment plan availability",
            "Return ranked, explained recommendations with caveats",
        ],
        implementation_status=ImplementationStatus.FUNCTIONAL,
        allowed_tools=frozenset({"property.match", "property.search"}),
        status_notes="Runs on the fictional demo catalog until an authorized data source is connected.",
    )
    input_model = RecommendationInput
    output_model = RecommendationOutput

    async def execute(
        self, data: RecommendationInput, ctx: ExecutionContext
    ) -> RecommendationOutput:
        result = await self.use_tool(ctx, "property.match", data.criteria.model_dump(mode="json"))
        recs = [PropertyRecommendation.model_validate(r) for r in result.data["recommendations"]]
        return RecommendationOutput(
            recommendations=recs,
            contains_demo_data=any(r.listing.is_demo for r in recs),
            no_match_reason=None if recs else "No eligible listings match the stated criteria.",
        )
