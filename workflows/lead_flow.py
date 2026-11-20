"""Workflow 01 - Lead Processing (functional end-to-end with mocks).

Lead Received -> Validate/Normalize/Deduplicate -> Duplicate gate -> Qualify -> Route -> Store in CRM
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.crm.schemas import CRMUpsertInput, CRMUpsertResult
from agents.lead_intake.schemas import LeadIntakeResult
from agents.qualification.schemas import QualificationInput, QualificationResult
from schemas.agents.models import ImplementationStatus
from schemas.leads.models import LeadRouting, LeadSubmission, NormalizedLead
from workflows.engine.core import (
    Step,
    StepOutcome,
    WorkflowContext,
    WorkflowDefinition,
    outcome_for,
)


class LeadFlowState(BaseModel):
    submission: LeadSubmission
    lead: NormalizedLead | None = None
    is_duplicate: bool = False
    duplicate_of: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    qualification: QualificationResult | None = None
    routing: LeadRouting | None = None
    crm: CRMUpsertResult | None = None


async def intake(state: LeadFlowState, ctx: WorkflowContext) -> StepOutcome:
    result = await ctx.run_agent("lead_intake", state.submission)
    output = LeadIntakeResult.model_validate(result.output, from_attributes=True)
    state.lead = output.lead
    state.is_duplicate = output.is_duplicate
    state.duplicate_of = output.duplicate_of
    state.warnings = output.warnings
    return StepOutcome.CONTINUE


async def duplicate_gate(state: LeadFlowState, ctx: WorkflowContext) -> StepOutcome:
    # Duplicates are not re-qualified or re-sent to the CRM; staff merge them.
    return StepOutcome.COMPLETE if state.is_duplicate else StepOutcome.CONTINUE


async def qualify(state: LeadFlowState, ctx: WorkflowContext) -> StepOutcome:
    assert state.lead is not None
    result = await ctx.run_agent("qualification", QualificationInput(lead=state.lead))
    state.qualification = QualificationResult.model_validate(result.output, from_attributes=True)
    state.lead = state.lead.model_copy(update={"status": state.qualification.status})
    return StepOutcome.CONTINUE


async def route(state: LeadFlowState, ctx: WorkflowContext) -> StepOutcome:
    assert state.qualification is not None
    state.routing = state.qualification.routing
    return StepOutcome.CONTINUE


async def store_in_crm(state: LeadFlowState, ctx: WorkflowContext) -> StepOutcome:
    assert state.lead is not None and state.qualification is not None
    result = await ctx.run_agent(
        "crm",
        CRMUpsertInput(lead=state.lead, score=state.qualification.score, routing=state.routing),
    )
    state.crm = CRMUpsertResult.model_validate(result.output, from_attributes=True)
    return outcome_for(result)


LEAD_PROCESSING = WorkflowDefinition(
    workflow_id="lead_processing",
    name="Lead Processing",
    description="Validate, normalize, de-duplicate, qualify, route and store inbound leads.",
    implementation_status=ImplementationStatus.FUNCTIONAL,
    state_model=LeadFlowState,
    steps=(
        Step("validate_normalize_deduplicate", intake),
        Step("duplicate_gate", duplicate_gate),
        Step("qualify", qualify),
        Step("route", route),
        Step("store_in_crm", store_in_crm),
    ),
)
