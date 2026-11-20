from __future__ import annotations

from typing import ClassVar

from agents.base.agent import AgentSpec, BaseAgent
from agents.base.context import ExecutionContext
from agents.email.schemas import EmailAgentInput, EmailAgentOutput, EmailMode, InboundClassification
from core.exceptions.errors import DomainValidationError
from schemas.agents.models import AgentRunStatus, ImplementationStatus

_CLASS_RULES: tuple[tuple[InboundClassification, tuple[str, ...]], ...] = (
    (InboundClassification.UNSUBSCRIBE, ("unsubscribe", "remove me", "stop emailing")),
    (InboundClassification.OUT_OF_OFFICE, ("out of office", "on leave", "auto-reply", "automatic reply")),
    (InboundClassification.NOT_INTERESTED, ("not interested", "no longer looking", "already bought")),
    (InboundClassification.INTERESTED, ("interested", "yes please", "send me", "call me", "book")),
)


def classify_inbound(text: str) -> InboundClassification:
    lowered = text.lower()
    for label, keywords in _CLASS_RULES:
        if any(k in lowered for k in keywords):
            return label
    return InboundClassification.QUESTION if "?" in text else InboundClassification.OTHER


class EmailAgent(BaseAgent[EmailAgentInput, EmailAgentOutput]):
    spec: ClassVar[AgentSpec] = AgentSpec(
        agent_id="email",
        name="Email Agent",
        description="Prepares template-based email drafts, classifies replies, routes sends via approval.",
        responsibilities=[
            "Generate professional email drafts from approved templates",
            "Classify inbound responses",
            "Route outbound messages through approval workflows",
        ],
        implementation_status=ImplementationStatus.PARTIAL,
        allowed_tools=frozenset({"email.render_template", "email.send"}),
        status_notes="No email provider configured (mock sender). LLM-written emails pending.",
    )
    input_model = EmailAgentInput
    output_model = EmailAgentOutput

    async def execute(self, data: EmailAgentInput, ctx: ExecutionContext) -> EmailAgentOutput:
        if data.mode == EmailMode.CLASSIFY:
            if not data.inbound_text:
                raise DomainValidationError("inbound_text is required for classification")
            return EmailAgentOutput(classification=classify_inbound(data.inbound_text))

        if not data.template:
            raise DomainValidationError("template is required")
        rendered = await self.use_tool(
            ctx,
            "email.render_template",
            {
                "template": data.template,
                "values": {"first_name": data.first_name, "advisor_name": data.advisor_name},
            },
        )
        subject, body = rendered.data["subject"], rendered.data["body"]
        if data.mode == EmailMode.DRAFT:
            return EmailAgentOutput(subject=subject, body=body)

        if not data.recipient_email:
            raise DomainValidationError("recipient_email is required to send")
        sent = await self.use_tool(
            ctx,
            "email.send",
            {
                "to": str(data.recipient_email),
                "subject": subject,
                "body": body,
                "is_marketing": data.is_marketing,
                "consent_marketing": data.consent_marketing,
            },
            reason=f"Send '{data.template}' email",
        )
        return EmailAgentOutput(
            subject=subject, body=body, send_status=sent.status.value, approval_id=sent.approval_id
        )

    def outcome_status(self, output: EmailAgentOutput) -> AgentRunStatus:
        if output.send_status == "pending_approval":
            return AgentRunStatus.PENDING_APPROVAL
        return AgentRunStatus.SUCCEEDED
