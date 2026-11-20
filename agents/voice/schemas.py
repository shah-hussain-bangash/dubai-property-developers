from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.conversations.models import CustomerIntent


class VoiceAgentInput(BaseModel):
    call_id: str
    transcript: str | None = Field(default=None, max_length=50_000)
    audio_uri: str | None = None


class VoiceAgentOutput(BaseModel):
    call_id: str
    intent: CustomerIntent
    summary: str
    appointment_requested: bool
    escalate_to_human: bool = True
