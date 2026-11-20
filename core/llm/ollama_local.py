"""Desktop-local Qwen3 adapter. No API key, cloud model or endpoint override."""

from __future__ import annotations

import json
import math

import httpx

from core.exceptions.errors import (
    ConfigurationError,
    DomainValidationError,
    IntegrationError,
    IntegrationNotConfiguredError,
)
from core.llm.types import LLMRequest, LLMResponse


class OllamaLocalProvider:
    name = "ollama"
    model = "qwen3:8b"
    _url = "http://127.0.0.1:11434/api/chat"
    _max_response_bytes = 2 * 1024 * 1024

    def __init__(self, *, timeout_seconds=120, transport=None, connection="native"):
        endpoints = {
            "native": "http://127.0.0.1:11434/api/chat",
            "docker-desktop": "http://host.docker.internal:11434/api/chat",
        }
        if not isinstance(connection, str) or connection not in endpoints:
            raise ConfigurationError("Unsupported local Ollama connection.")
        self._url = endpoints[connection]
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 180
        ):
            raise ConfigurationError("Local Ollama timeout must be between zero and 180 seconds.")
        self._timeout = timeout_seconds
        self._transport = transport

    async def complete(self, request: LLMRequest, *, model: str) -> LLMResponse:
        if model != self.model:
            raise DomainValidationError("This local adapter requires the installed qwen3:8b model.")
        if (
            not request.messages
            or len(request.messages) > 100
            or any(not message.content.strip() for message in request.messages)
            or sum(len(message.content) for message in request.messages) > 8000
            or not 1 <= request.max_output_tokens <= 2048
            or not math.isfinite(request.temperature)
            or not 0 <= request.temperature <= 2
        ):
            raise DomainValidationError(
                "Local Ollama request is empty or exceeds supported limits."
            )
        payload = {
            "model": model,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "stream": False,
            "think": False,
            "keep_alive": "5m",
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_output_tokens,
                "num_ctx": 4096,
            },
        }
        data = bytearray()
        try:
            async with (
                httpx.AsyncClient(
                    transport=self._transport,
                    timeout=self._timeout,
                    trust_env=False,
                    follow_redirects=False,
                ) as client,
                client.stream("POST", self._url, json=payload) as response,
            ):
                if response.status_code == 404:
                    raise IntegrationNotConfiguredError(
                        "Local Ollama model is not available. Install qwen3:8b."
                    )
                if response.status_code != 200:
                    raise IntegrationError("Local Ollama rejected the request.")
                if (
                    response.headers.get("content-type", "").split(";")[0].strip().lower()
                    != "application/json"
                ):
                    raise IntegrationError("Local Ollama returned an unsupported response format.")
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > self._max_response_bytes:
                        raise IntegrationError("Local Ollama response exceeded the size limit.")
                    data.extend(chunk)
        except httpx.HTTPError:
            raise IntegrationError(
                "Local Ollama is unavailable or the request timed out."
            ) from None
        try:
            body = json.loads(data)
            if (
                not isinstance(body, dict)
                or body.get("error")
                or body.get("model") != model
                or body.get("done") is not True
                or body.get("done_reason") != "stop"
            ):
                raise ValueError
            message = body["message"]
            if (
                not isinstance(message, dict)
                or message.get("role") != "assistant"
                or message.get("tool_calls")
                or not isinstance(message.get("content"), str)
                or not message["content"].strip()
            ):
                raise ValueError
            counts = [body["prompt_eval_count"], body["eval_count"]]
            if any(type(value) is not int or not 0 <= value <= 1000000000 for value in counts):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise IntegrationError(
                "Local Ollama returned an incomplete or invalid text response."
            ) from None
        return LLMResponse(
            text=message["content"],
            provider=self.name,
            model=model,
            input_tokens=counts[0],
            output_tokens=counts[1],
            finish_reason="stop",
            is_mock=False,
        )
