"""Workflow 04 - Follow-Up Automation.

Follow-Up Due -> Check Consent and Status -> Prepare Message -> Approval if Required
-> Send (after approval, via ToolGateway.execute_approved) -> Record Result
"""

from __future__ import annotations

from pydantic import BaseModel

from agents.followup.schemas import FollowUpInput, FollowUpPlan
from schemas.agents.models import ImplementationStatus
from workflows.engine.core import Step, StepOutcome, WorkflowContext, WorkflowDefinition, outcome_for


class FollowUpFlowState(BaseModel):
    request: FollowUpInput
    plan: FollowUpPlan | None = None


async def plan_and_request(state: FollowUpFlowState, ctx: WorkflowContext) -> StepOutcome:
    request = state.request.model_copy(update={"dispatch": True})
    result = await ctx.run_agent("followup", request)
    state.plan = FollowUpPlan.model_validate(result.output, from_attributes=True)
    return outcome_for(result)


FOLLOWUP_AUTOMATION = WorkflowDefinition(
    workflow_id="followup_automation",
    name="Follow-Up Automation",
    description="Check due follow-ups, verify consent/status, prepare messages and request "
    "approval-gated sends; escalate overdue items.",
    implementation_status=ImplementationStatus.PARTIAL,
    state_model=FollowUpFlowState,
    steps=(Step("check_prepare_request_approval", plan_and_request),),
)
