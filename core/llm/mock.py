"""Deterministic offline LLM provider for local development and tests.

It does NOT generate intelligent output. It returns either a scripted response
(matched by a ``metadata['task']`` key) or a clearly labelled placeholder.
"""

from __future__ import annotations

from core.llm.types import LLMRequest, LLMResponse


class MockLLMProvider:
    name = "mock"

    def __init__(self, scripted: dict[str, str] | None = None, *, fail_times: int = 0) -> None:
        self._scripted = scripted or {}
        self._fail_times = fail_times
        self.calls: list[LLMRequest] = []

    async def complete(self, request: LLMRequest, *, model: str) -> LLMResponse:
        self.calls.append(request)
        if self._fail_times > 0:
            self._fail_times -= 1
            raise ConnectionError("mock provider configured to fail")
        task = str(request.metadata.get("task", ""))
        text = self._scripted.get(task) or f"[MOCK LLM OUTPUT for task '{task or 'unspecified'}']"
        prompt_words = sum(len(m.content.split()) for m in request.messages)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=model,
            input_tokens=prompt_words,
            output_tokens=len(text.split()),
            is_mock=True,
        )
