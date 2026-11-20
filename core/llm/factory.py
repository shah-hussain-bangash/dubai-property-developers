from __future__ import annotations

import math
import re

from core.config.settings import Settings
from core.exceptions.errors import ConfigurationError
from core.llm.base import LLMProvider
from core.llm.mock import MockLLMProvider
from core.llm.router import ModelRouter, ModelTarget
from core.resilience.retry import RetryPolicy


def build_model_router(settings: Settings) -> ModelRouter:
    """Keep mock as default; construct OpenAI only after explicit validation.

    Construction makes no request. OpenAI generation requires a later call to
    router.complete. Model defaults apply to temperature in this registration.
    """
    if settings.llm_provider == "mock":
        providers: dict[str, LLMProvider] = {"mock": MockLLMProvider()}
        provider_name = "mock"
    elif settings.llm_provider == "ollama":
        if settings.llm_primary_model != "qwen3:8b" or settings.llm_fallback_models:
            raise ConfigurationError("Local Ollama requires qwen3:8b and no fallback models.")
        if (
            not math.isfinite(settings.llm_timeout_seconds)
            or not 0 < settings.llm_timeout_seconds <= 180
            or not 0 <= settings.llm_max_retries <= 2
        ):
            raise ConfigurationError("Local Ollama timeout or retry settings are invalid.")
        from core.llm.ollama_local import OllamaLocalProvider

        providers = {"ollama": OllamaLocalProvider(timeout_seconds=settings.llm_timeout_seconds)}
        provider_name = "ollama"
    elif settings.llm_provider == "openai":
        models = [settings.llm_primary_model, *settings.llm_fallback_models]
        if len(models) > 5 or any(
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}", model)
            or model.lower().startswith("mock")
            for model in models
        ):
            raise ConfigurationError(
                "OpenAI requires explicit primary and fallback model identifiers."
            )
        if (
            not math.isfinite(settings.llm_timeout_seconds)
            or not 0 < settings.llm_timeout_seconds <= 120
        ):
            raise ConfigurationError("OpenAI timeout must be between zero and 120 seconds.")
        if not 0 <= settings.llm_max_retries <= 3:
            raise ConfigurationError("OpenAI retries must be between zero and three.")
        if settings.llm_api_key is None:
            raise ConfigurationError("OpenAI requires a privately supplied API key.")
        # Lazy import keeps the default mock path independent of the adapter.
        from core.llm.openai_responses import OpenAIResponsesProvider

        providers = {
            "openai": OpenAIResponsesProvider(
                settings.llm_api_key,
                timeout_seconds=settings.llm_timeout_seconds,
            )
        }
        provider_name = "openai"
    else:
        raise ConfigurationError("Unsupported LLM provider. Use mock, ollama or openai.")
    chain = [ModelTarget(provider_name, settings.llm_primary_model)]
    chain += [ModelTarget(provider_name, model) for model in settings.llm_fallback_models]
    return ModelRouter(
        providers,
        chain,
        retry_policy=RetryPolicy(
            max_attempts=settings.llm_max_retries + 1,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
    )
