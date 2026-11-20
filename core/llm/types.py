from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from core.observability.usage import TokenUsage


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    role: ChatRole
    content: str


class LLMRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None  # None = router chooses primary model
    temperature: float = 0.2
    max_output_tokens: int = 800
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"
    is_mock: bool = False

    @property
    def usage(self) -> TokenUsage:
        return TokenUsage(self.input_tokens, self.output_tokens)
