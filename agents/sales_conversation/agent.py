"""Sales Conversation Agent.

Detect intent -> retrieve authorized public context -> draft from approved
templates -> apply policy -> return a draft that always requires approval, or an
escalation. LLM-generated drafting is a planned upgrade behind ``deps.llm``.
"""

from __future__ import annotations

from typing import ClassVar

from agents.base.agent import AgentSpec, BaseAgent
from agents.base.context import ExecutionContext
from agents.base.intent import detect_intent, detect_language
from agents.sales_conversation.schemas import SalesConversationInput, SalesConversationOutput
from agents.sales_conversation.templates import ESCALATION_ACK, render_reply
from core.memory.base import MemoryMessage
from core.policies.prompt_safety import assess_injection
from core.security.sanitization import sanitize_text
from knowledge.assigned_sources import NO_ANSWER
from schemas.agents.models import AgentRunStatus, ImplementationStatus
from schemas.conversations.models import Citation, CustomerIntent, DraftReply

MIN_CONTEXT_SCORE = 0.15
_ESCALATE_INTENTS = {CustomerIntent.COMPLAINT, CustomerIntent.UNSUBSCRIBE}
_CONTEXT_INTENTS = {CustomerIntent.PAYMENT_PLAN, CustomerIntent.PROPERTY_ENQUIRY}


class SalesConversationAgent(BaseAgent[SalesConversationInput, SalesConversationOutput]):
    spec: ClassVar[AgentSpec] = AgentSpec(
        agent_id="sales_conversation",
        name="Sales Conversation Agent",
        description="Drafts policy-compliant replies to customer enquiries or escalates to staff.",
        responsibilities=[
            "Handle customer enquiries and project questions",
            "Explain payment plans using cited documents",
            "Support English and Arabic replies",
            "Prepare meeting requests",
            "Hand conversations to human sales agents",
        ],
        implementation_status=ImplementationStatus.PARTIAL,
        allowed_tools=frozenset({"documents.search"}),
        status_notes="Template-based drafts; LLM drafting and full multilingual support pending.",
    )
    input_model = SalesConversationInput
    output_model = SalesConversationOutput

    async def execute(
        self, data: SalesConversationInput, ctx: ExecutionContext
    ) -> SalesConversationOutput:
        text = sanitize_text(data.message.text)
        intent = detect_intent(text)
        language = data.message.language or detect_language(text)
        injection = assess_injection(text)
        name = data.customer_first_name or "there"

        await self.deps.memory.append(
            data.message.conversation_id,
            MemoryMessage(role="customer", content=text, channel=data.message.channel.value),
        )

        if intent in _ESCALATE_INTENTS or injection.suspicious:
            reason = (
                f"intent '{intent.value}' requires human handling"
                if intent in _ESCALATE_INTENTS
                else "message flagged by prompt-injection heuristics"
            )
            draft = DraftReply(
                text=ESCALATION_ACK.get(language, ESCALATION_ACK["en"]).format(name=name),
                channel=data.message.channel,
                language=language,
                escalate=True,
                escalation_reason=reason,
                is_template=True,
            )
            return SalesConversationOutput(
                intent=intent,
                language=language,
                draft=draft,
                injection_signals=list(injection.signals),
            )

        citations: list[Citation] = []
        context = ""
        top_score = 0.0
        if intent in _CONTEXT_INTENTS or self.deps.supplied_knowledge_only:
            result = await self.use_tool(
                ctx,
                "documents.search",
                {"query": text, "tenant_id": ctx.tenant_id, "audience": "customer", "k": 2},
            )
            top_score = float(result.data.get("top_score", 0.0))
            if top_score >= MIN_CONTEXT_SCORE and not result.data.get("has_stale"):
                citations = [Citation.model_validate(c) for c in result.data["citations"]]
                context = "\n".join(result.data["passages"][:1])

        escalate = (
            intent == CustomerIntent.PAYMENT_PLAN or self.deps.supplied_knowledge_only
        ) and not citations
        draft = DraftReply(
            text=(context if citations else NO_ANSWER)
            if self.deps.supplied_knowledge_only
            else render_reply(
                language, intent if not escalate else CustomerIntent.GENERAL, name, context
            ),
            channel=data.message.channel,
            language=language,
            requires_approval=True,
            escalate=escalate,
            escalation_reason="no authorized, current document answers this question"
            if escalate
            else None,
            citations=citations,
            is_template=True,
        )
        return SalesConversationOutput(
            intent=intent, language=language, draft=draft, retrieval_top_score=top_score
        )

    def outcome_status(self, output: SalesConversationOutput) -> AgentRunStatus:
        return AgentRunStatus.ESCALATED if output.draft.escalate else AgentRunStatus.SUCCEEDED
