"""Workflow 03 - Sales Conversation.

Customer Message -> Detect Intent -> Retrieve Context + Generate Draft -> Apply Policy
-> Reply (approval-gated) or Escalate
"""

from __future__ import annotations

from pydantic import BaseModel

from agents.sales_conversation.schemas import SalesConversationInput, SalesConversationOutput
from agents.supervisor.schemas import RequestType, SupervisorPlan, SupervisorRequest
from agents.whatsapp.schemas import WhatsAppAgentInput, WhatsAppAgentOutput
from schemas.agents.models import ImplementationStatus
from schemas.conversations.models import Channel, ConversationMessage
from workflows.engine.core import (
    Step,
    StepOutcome,
    WorkflowContext,
    WorkflowDefinition,
    outcome_for,
)


class SalesFlowState(BaseModel):
    message: ConversationMessage
    customer_first_name: str | None = None
    customer_e164: str | None = None
    consent_whatsapp: bool = False
    plan: SupervisorPlan | None = None
    reply: SalesConversationOutput | None = None
    whatsapp: WhatsAppAgentOutput | None = None


async def detect_intent(state: SalesFlowState, ctx: WorkflowContext) -> StepOutcome:
    result = await ctx.run_agent(
        "supervisor",
        SupervisorRequest(
            request_type=RequestType.CUSTOMER_MESSAGE, text=state.message.text, channel=state.message.channel
        ),
    )
    state.plan = SupervisorPlan.model_validate(result.output, from_attributes=True)
    return StepOutcome.CONTINUE  # sales agent still prepares an acknowledgement on escalation


async def draft_reply(state: SalesFlowState, ctx: WorkflowContext) -> StepOutcome:
    result = await ctx.run_agent(
        "sales_conversation",
        SalesConversationInput(message=state.message, customer_first_name=state.customer_first_name),
    )
    state.reply = SalesConversationOutput.model_validate(result.output, from_attributes=True)
    if state.reply.draft.escalate or (state.plan and state.plan.requires_human):
        return StepOutcome.ESCALATE
    return StepOutcome.CONTINUE


async def dispatch(state: SalesFlowState, ctx: WorkflowContext) -> StepOutcome:
    assert state.reply is not None
    if state.message.channel != Channel.WHATSAPP or not state.customer_e164:
        # Other channels: the approved draft is handed to staff/UI for sending.
        return StepOutcome.PENDING_APPROVAL
    result = await ctx.run_agent(
        "whatsapp",
        WhatsAppAgentInput(
            conversation_id=state.message.conversation_id,
            from_e164=state.customer_e164,
            text=state.message.text,
            received_at=state.message.sent_at,
            consent_whatsapp=state.consent_whatsapp,
            customer_first_name=state.customer_first_name,
            draft_reply=state.reply.draft.text,
            send_reply=True,
        ),
    )
    state.whatsapp = WhatsAppAgentOutput.model_validate(result.output, from_attributes=True)
    outcome = outcome_for(result)
    return StepOutcome.PENDING_APPROVAL if outcome == StepOutcome.CONTINUE else outcome


SALES_CONVERSATION = WorkflowDefinition(
    workflow_id="sales_conversation",
    name="Sales Conversation",
    description="Detect intent, retrieve authorized context, draft a policy-checked reply, then "
    "request approval to send or escalate to staff.",
    implementation_status=ImplementationStatus.PARTIAL,
    state_model=SalesFlowState,
    steps=(
        Step("detect_intent", detect_intent),
        Step("retrieve_context_and_draft", draft_reply),
        Step("approve_and_dispatch", dispatch),
    ),
)
