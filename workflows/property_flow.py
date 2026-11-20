"""Workflow 02 - Property Recommendation.

Customer Requirements -> Search + Eligibility Filtering + Ranking -> Compliance check -> Output
"""

from __future__ import annotations

from pydantic import BaseModel

from agents.property_recommendation.schemas import RecommendationInput, RecommendationOutput
from core.exceptions.errors import PolicyViolationError
from schemas.agents.models import ImplementationStatus
from schemas.properties.models import PropertySearchCriteria
from workflows.engine.core import Step, StepOutcome, WorkflowContext, WorkflowDefinition


class PropertyFlowState(BaseModel):
    criteria: PropertySearchCriteria
    output: RecommendationOutput | None = None


async def recommend(state: PropertyFlowState, ctx: WorkflowContext) -> StepOutcome:
    result = await ctx.run_agent(
        "property_recommendation", RecommendationInput(criteria=state.criteria)
    )
    state.output = RecommendationOutput.model_validate(result.output, from_attributes=True)
    return StepOutcome.CONTINUE


async def compliance_check(state: PropertyFlowState, ctx: WorkflowContext) -> StepOutcome:
    assert state.output is not None
    for rec in state.output.recommendations:
        if not any("guaranteed" in c for c in rec.caveats):
            raise PolicyViolationError(
                f"recommendation {rec.listing.listing_id} lacks ROI disclaimer"
            )
        if rec.listing.is_demo and not any("DEMO DATA" in c for c in rec.caveats):
            raise PolicyViolationError("demo listing not labelled as demo")
    return StepOutcome.CONTINUE


PROPERTY_RECOMMENDATION = WorkflowDefinition(
    workflow_id="property_recommendation",
    name="Property Recommendation",
    description="Search, filter, rank and explain properties against customer requirements.",
    implementation_status=ImplementationStatus.FUNCTIONAL,
    state_model=PropertyFlowState,
    steps=(Step("search_filter_rank", recommend), Step("compliance_check", compliance_check)),
)
