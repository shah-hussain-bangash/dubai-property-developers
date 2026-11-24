from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from agents.base.agent import AgentSpec, BaseAgent
from agents.base.context import ExecutionContext
from agents.base.intent import detect_intent
from agents.whatsapp.schemas import ReplyMode, WhatsAppAgentInput, WhatsAppAgentOutput
from core.memory.base import MemoryMessage
from knowledge.assigned_sources import NO_ANSWER
from schemas.agents.models import AgentRunStatus, ImplementationStatus
from schemas.conversations.models import Citation, CustomerIntent
from tools.whatsapp.policy import is_within_service_window

FALLBACK_TEMPLATE = "follow_up_generic"


class WhatsAppAgent(BaseAgent[WhatsAppAgentInput, WhatsAppAgentOutput]):
    spec: ClassVar[AgentSpec] = AgentSpec(
        agent_id="whatsapp",
        name="WhatsApp Agent",
        description="Handles WhatsApp Business events with opt-in, 24h window and template rules.",
        responsibilities=[
            "Process WhatsApp Business API events",
            "Maintain conversation state",
            "Prepare contextual replies within messaging rules",
            "Use approved templates outside the service window",
            "Escalate conversations to staff",
        ],
        implementation_status=ImplementationStatus.PARTIAL,
        allowed_tools=frozenset({"whatsapp.send_message", "documents.search"}),
        status_notes="Supplied-source replies quote approved own material inside the service window; "
        "outside-window replies escalate. Mock Cloud API; template catalogue sync pending.",
    )
    input_model = WhatsAppAgentInput
    output_model = WhatsAppAgentOutput

    async def execute(self, data: WhatsAppAgentInput, ctx: ExecutionContext) -> WhatsAppAgentOutput:
        intent = detect_intent(data.text)
        memory = self.conversation_memory(ctx)
        await memory.append(
            data.conversation_id,
            MemoryMessage(role="customer", content=data.text, channel="whatsapp"),
        )
        state = await memory.get_state(data.conversation_id)
        state["last_inbound_at"] = data.received_at.isoformat()

        if intent == CustomerIntent.UNSUBSCRIBE:
            state["opted_out"] = True
            await memory.set_state(data.conversation_id, state)
            return WhatsAppAgentOutput(
                intent=intent,
                reply_mode=ReplyMode.NO_REPLY,
                escalate=True,
                notes=[
                    "Customer opted out: record consent withdrawal in CRM; no further messages."
                ],
            )
        await memory.set_state(data.conversation_id, state)

        if not data.consent_whatsapp or state.get("opted_out"):
            return WhatsAppAgentOutput(
                intent=intent,
                reply_mode=ReplyMode.NO_REPLY,
                escalate=True,
                notes=["No WhatsApp opt-in on record; staff must follow up via another channel."],
            )

        in_window = is_within_service_window(data.received_at, datetime.now(UTC))
        citations: list[Citation] = []
        reply_text = data.draft_reply
        if self.deps.supplied_knowledge_only:
            if not in_window or intent == CustomerIntent.COMPLAINT:
                return WhatsAppAgentOutput(
                    intent=intent,
                    reply_mode=ReplyMode.NO_REPLY,
                    escalate=True,
                    notes=[
                        "Staff review is required; approved WhatsApp provider templates are not "
                        "configured for supplied-source replies."
                        if not in_window
                        else "Customer complaint requires staff review."
                    ],
                )
            result = await self.use_tool(
                ctx,
                "documents.search",
                {
                    "query": data.text,
                    "tenant_id": ctx.tenant_id,
                    "audience": "customer",
                    "k": 3,
                },
            )
            if not result.data.get("has_stale"):
                citations = [Citation.model_validate(c) for c in result.data.get("citations", [])]
            if not citations:
                return WhatsAppAgentOutput(
                    intent=intent, reply_mode=ReplyMode.NO_REPLY, escalate=True, notes=[NO_ANSWER]
                )
            reply_text = "\n\n".join(c.excerpt for c in citations)
        mode = ReplyMode.FREE_TEXT if in_window else ReplyMode.TEMPLATE_REQUIRED
        output = WhatsAppAgentOutput(
            intent=intent,
            reply_mode=mode,
            reply_text=reply_text if mode == ReplyMode.FREE_TEXT else None,
            template_name=FALLBACK_TEMPLATE if mode == ReplyMode.TEMPLATE_REQUIRED else None,
            escalate=intent == CustomerIntent.COMPLAINT,
            citations=citations,
        )
        if data.send_reply and (output.reply_text or output.template_name) and not output.escalate:
            payload: dict[str, Any] = {
                "to_e164": data.from_e164,
                "consent_whatsapp": data.consent_whatsapp,
                "last_inbound_at": data.received_at.isoformat(),
                "idempotency_key": f"{data.conversation_id}:{data.received_at.isoformat()}",
            }
            if output.reply_text:
                payload["text"] = output.reply_text
            else:
                payload["template_name"] = output.template_name
                payload["language_code"] = "en"
            if self.deps.supplied_knowledge_only:
                payload["knowledge_citations"] = [c.model_dump() for c in citations]
            sent = await self.use_tool(
                ctx, "whatsapp.send_message", payload, reason="Reply to customer"
            )
            output.send_status = sent.status.value
            output.approval_id = sent.approval_id
        return output

    def outcome_status(self, output: WhatsAppAgentOutput) -> AgentRunStatus:
        if output.escalate:
            return AgentRunStatus.ESCALATED
        if output.send_status == "pending_approval":
            return AgentRunStatus.PENDING_APPROVAL
        return AgentRunStatus.SUCCEEDED
