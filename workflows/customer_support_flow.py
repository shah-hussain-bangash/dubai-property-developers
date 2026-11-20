"""Workflow 06 - Knowledge-Based Support.

Customer Question -> Retrieve Authorized Documents -> Prepare Cited Answer
-> Confidence Evaluation -> Response (approval-gated) or Human Handoff
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.documents.schemas import DocumentAction, DocumentAgentInput, DocumentAgentOutput
from schemas.agents.models import ImplementationStatus
from workflows.engine.core import Step, StepOutcome, WorkflowContext, WorkflowDefinition


class SupportFlowState(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    audience: str = Field(default="customer", pattern="^(customer|staff)$")
    answer: DocumentAgentOutput | None = None


async def retrieve_and_answer(state: SupportFlowState, ctx: WorkflowContext) -> StepOutcome:
    result = await ctx.run_agent(
        "documents",
        DocumentAgentInput(
            action=DocumentAction.ANSWER, query=state.question, audience=state.audience
        ),
    )
    state.answer = DocumentAgentOutput.model_validate(result.output, from_attributes=True)
    return StepOutcome.CONTINUE


async def confidence_gate(state: SupportFlowState, ctx: WorkflowContext) -> StepOutcome:
    assert state.answer is not None
    if state.answer.needs_human:
        return StepOutcome.ESCALATE
    # Customer-facing answers are drafts until a human approves sending.
    return StepOutcome.PENDING_APPROVAL if state.audience == "customer" else StepOutcome.CONTINUE


KNOWLEDGE_SUPPORT = WorkflowDefinition(
    workflow_id="knowledge_support",
    name="Knowledge-Based Support",
    description="Answer questions from authorized documents with citations, or hand off to a human.",
    implementation_status=ImplementationStatus.PARTIAL,
    state_model=SupportFlowState,
    steps=(
        Step("retrieve_and_prepare_cited_answer", retrieve_and_answer),
        Step("confidence_evaluation", confidence_gate),
    ),
)
