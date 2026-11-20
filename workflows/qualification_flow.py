"""Re-qualification sub-flow for an existing normalized lead (e.g. after new info)."""

from __future__ import annotations

from pydantic import BaseModel

from agents.qualification.schemas import QualificationInput, QualificationResult
from schemas.agents.models import ImplementationStatus
from schemas.leads.models import NormalizedLead
from workflows.engine.core import Step, StepOutcome, WorkflowContext, WorkflowDefinition


class QualificationFlowState(BaseModel):
    lead: NormalizedLead
    result: QualificationResult | None = None


async def qualify(state: QualificationFlowState, ctx: WorkflowContext) -> StepOutcome:
    result = await ctx.run_agent("qualification", QualificationInput(lead=state.lead))
    state.result = QualificationResult.model_validate(result.output, from_attributes=True)
    return StepOutcome.CONTINUE


LEAD_REQUALIFICATION = WorkflowDefinition(
    workflow_id="lead_requalification",
    name="Lead Re-qualification",
    description="Re-score and re-route an existing lead.",
    implementation_status=ImplementationStatus.FUNCTIONAL,
    state_model=QualificationFlowState,
    steps=(Step("qualify_and_route", qualify),),
)
