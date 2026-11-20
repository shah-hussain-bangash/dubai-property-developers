"""Supervisor Agent: classifies requests and plans which workflow/agents handle them.

Execution of the plan is performed by the workflow engine (``workflows/``), so
orchestration logic exists in exactly one place.
"""

from __future__ import annotations

from typing import ClassVar

from agents.base.agent import AgentSpec, BaseAgent
from agents.base.context import ExecutionContext
from agents.base.intent import detect_intent
from agents.supervisor.schemas import RequestType, SupervisorPlan, SupervisorRequest
from core.policies.prompt_safety import assess_injection
from schemas.agents.models import AgentRunStatus, ImplementationStatus
from schemas.conversations.models import Channel, CustomerIntent

_ROUTES: dict[RequestType, tuple[str | None, list[str]]] = {
    RequestType.LEAD_SUBMISSION: ("lead_processing", ["lead_intake", "qualification", "crm"]),
    RequestType.PROPERTY_SEARCH: ("property_recommendation", ["property_recommendation"]),
    RequestType.FOLLOWUP_DUE: ("followup_automation", ["followup"]),
    RequestType.CRM_EVENT: ("crm_sync", ["crm"]),
    RequestType.KNOWLEDGE_QUESTION: ("knowledge_support", ["documents"]),
    RequestType.ANALYTICS: (None, ["analytics"]),
}

_HUMAN_INTENTS = {CustomerIntent.COMPLAINT, CustomerIntent.UNSUBSCRIBE}


class SupervisorAgent(BaseAgent[SupervisorRequest, SupervisorPlan]):
    spec: ClassVar[AgentSpec] = AgentSpec(
        agent_id="supervisor",
        name="Supervisor Agent",
        description="Identifies business intent, selects workflows and agents, escalates sensitive requests.",
        responsibilities=[
            "Receive user and system requests",
            "Identify business intent",
            "Select specialized agents and workflows",
            "Escalate sensitive requests for human handling",
        ],
        implementation_status=ImplementationStatus.FUNCTIONAL,
        allowed_tools=frozenset(),
        status_notes="Deterministic routing table + keyword intent; LLM routing planned.",
    )
    input_model = SupervisorRequest
    output_model = SupervisorPlan

    async def execute(self, data: SupervisorRequest, ctx: ExecutionContext) -> SupervisorPlan:
        if data.request_type != RequestType.CUSTOMER_MESSAGE:
            workflow_id, agents = _ROUTES[data.request_type]
            return SupervisorPlan(
                workflow_id=workflow_id,
                agent_sequence=agents,
                reasons=[f"request_type={data.request_type.value}"],
            )

        text = data.text or ""
        intent = detect_intent(text)
        injection = assess_injection(text)
        channel_agent = (
            "whatsapp"
            if data.channel == Channel.WHATSAPP
            else ("email" if data.channel == Channel.EMAIL else None)
        )
        agents = [a for a in (channel_agent, "sales_conversation") if a]
        reasons = [f"intent={intent.value}"]
        requires_human = intent in _HUMAN_INTENTS
        if requires_human:
            reasons.append("sensitive intent requires a human")
        if injection.suspicious:
            requires_human = True
            reasons.append("possible prompt-injection content")
        return SupervisorPlan(
            workflow_id="sales_conversation",
            agent_sequence=agents,
            intent=intent,
            requires_human=requires_human,
            reasons=reasons,
            injection_signals=list(injection.signals),
        )

    def outcome_status(self, output: SupervisorPlan) -> AgentRunStatus:
        return AgentRunStatus.ESCALATED if output.requires_human else AgentRunStatus.SUCCEEDED
