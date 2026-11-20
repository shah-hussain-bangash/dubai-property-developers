"""Voice AI Agent - INTERFACE ONLY.

No telephony or speech-to-text provider is configured. Audio input raises a
structured ``not_implemented`` error. A transcript-only path exists purely to
exercise the contract in tests; every call is escalated to a human.
"""

from __future__ import annotations

import re
from typing import ClassVar

from agents.base.agent import AgentSpec, BaseAgent
from agents.base.context import ExecutionContext
from agents.base.intent import detect_intent
from agents.voice.schemas import VoiceAgentInput, VoiceAgentOutput
from core.exceptions.errors import IntegrationNotConfiguredError
from schemas.agents.models import AgentRunStatus, ImplementationStatus
from schemas.conversations.models import CustomerIntent


class VoiceAgent(BaseAgent[VoiceAgentInput, VoiceAgentOutput]):
    spec: ClassVar[AgentSpec] = AgentSpec(
        agent_id="voice",
        name="Voice AI Agent",
        description="Future voice channel: transcription, intent, summary and human call escalation.",
        responsibilities=[
            "Speech-to-text processing (pending provider)",
            "Intent detection",
            "Conversation summarization",
            "Appointment request handling",
            "Human call escalation",
        ],
        implementation_status=ImplementationStatus.INTERFACE_ONLY,
        allowed_tools=frozenset(),
        status_notes="No telephony/STT provider selected. Transcript path is for contract tests only.",
    )
    input_model = VoiceAgentInput
    output_model = VoiceAgentOutput

    async def execute(self, data: VoiceAgentInput, ctx: ExecutionContext) -> VoiceAgentOutput:
        if not data.transcript:
            raise IntegrationNotConfiguredError("speech-to-text provider not configured")
        intent = detect_intent(data.transcript)
        sentences = re.split(r"(?<=[.!?])\s+", data.transcript.strip())
        return VoiceAgentOutput(
            call_id=data.call_id,
            intent=intent,
            summary=" ".join(sentences[:2])[:500],
            appointment_requested=intent
            in {CustomerIntent.SCHEDULE_VIEWING, CustomerIntent.CALLBACK_REQUEST},
        )

    def outcome_status(self, output: VoiceAgentOutput) -> AgentRunStatus:
        return AgentRunStatus.ESCALATED
