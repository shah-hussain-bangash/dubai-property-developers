from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.llm.types import LLMRequest, LLMResponse


@runtime_checkable
class LLMProvider(Protocol):
    """Adapter contract for any chat-completion provider."""

    name: str

    async def complete(self, request: LLMRequest, *, model: str) -> LLMResponse: ...
