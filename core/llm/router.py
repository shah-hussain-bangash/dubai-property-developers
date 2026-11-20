"""Model selection with retries and ordered fallbacks."""

from __future__ import annotations

from dataclasses import dataclass

from core.exceptions.errors import IntegrationError
from core.llm.base import LLMProvider
from core.llm.types import LLMRequest, LLMResponse
from core.observability.context import get_correlation_id
from core.observability.logging import get_logger
from core.observability.usage import InMemoryUsageTracker, UsageSink
from core.resilience.retry import RetryPolicy, retry_async

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ModelTarget:
    provider: str
    model: str


class ModelRouter:
    def __init__(
        self,
        providers: dict[str, LLMProvider],
        chain: list[ModelTarget],
        *,
        retry_policy: RetryPolicy | None = None,
        usage_sink: UsageSink | None = None,
    ) -> None:
        if not chain:
            raise ValueError("model chain must contain at least one target")
        self._providers = providers
        self._chain = chain
        self._retry = retry_policy or RetryPolicy()
        self.usage_sink: UsageSink = usage_sink or InMemoryUsageTracker()

    @property
    def primary(self) -> ModelTarget:
        return self._chain[0]

    async def complete(self, request: LLMRequest, *, agent_id: str = "unknown") -> LLMResponse:
        targets = self._chain
        if request.model:
            targets = [t for t in self._chain if t.model == request.model] or self._chain
        last_error: Exception | None = None
        for target in targets:
            provider = self._providers.get(target.provider)
            if provider is None:
                continue
            try:
                response = await retry_async(
                    lambda p=provider, m=target.model: p.complete(request, model=m), self._retry
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "llm target failed, trying fallback",
                    extra={
                        "provider": target.provider,
                        "model": target.model,
                        "error": type(exc).__name__,
                    },
                )
                continue
            self.usage_sink.record(
                agent_id=agent_id,
                model=response.model,
                usage=response.usage,
                correlation_id=get_correlation_id(),
            )
            return response
        raise IntegrationError("all LLM targets failed") from last_error
