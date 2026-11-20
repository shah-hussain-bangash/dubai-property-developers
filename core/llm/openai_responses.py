"""Text-only Responses API adapter. Registration and activation are separate.

Contract: https://developers.openai.com/api/docs/guides/text
The caller supplies a model; this module never selects a paid model implicitly.
Temperature is sent only when explicitly enabled for a compatible model.
"""

from __future__ import annotations

import json
import math
import re

import httpx
from pydantic import SecretStr

from core.exceptions.errors import (
    ConfigurationError,
    DomainValidationError,
    IntegrationError,
    IntegrationNotConfiguredError,
    RateLimitExceededError,
)
from core.llm.types import LLMRequest, LLMResponse


class OpenAIResponsesProvider:
    name = "openai"
    _url = "https://api.openai.com/v1/responses"
    _max_response_bytes = 2 * 1024 * 1024

    def __init__(
        self,
        api_key: SecretStr,
        *,
        timeout_seconds: float = 30,
        supports_temperature: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not isinstance(api_key, SecretStr):
            raise ConfigurationError("OpenAI API key must be supplied as a secret.")
        key = api_key.get_secret_value()
        if not key or key != key.strip() or any(ord(char) < 33 or ord(char) > 126 for char in key):
            raise ConfigurationError("OpenAI API key is missing or invalid.")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 120
        ):
            raise ConfigurationError("OpenAI timeout must be between zero and 120 seconds.")
        if not isinstance(supports_temperature, bool):
            raise ConfigurationError("OpenAI temperature capability must be explicit.")
        self._key = api_key
        self._timeout = timeout_seconds
        self._supports_temperature = supports_temperature
        self._transport = transport

    async def complete(self, request: LLMRequest, *, model: str) -> LLMResponse:
        if not isinstance(model, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}", model
        ):
            raise DomainValidationError("A valid OpenAI model identifier is required.")
        if (
            not request.messages
            or len(request.messages) > 100
            or any(not message.content.strip() for message in request.messages)
            or sum(len(message.content) for message in request.messages) > 100000
        ):
            raise DomainValidationError("OpenAI messages are empty or exceed the input limit.")
        if not 16 <= request.max_output_tokens <= 16384:
            raise DomainValidationError("OpenAI output token limit must be between 16 and 16384.")
        if not math.isfinite(request.temperature) or not 0 <= request.temperature <= 2:
            raise DomainValidationError("OpenAI temperature is outside the supported range.")
        payload = {
            "model": model,
            "input": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "max_output_tokens": request.max_output_tokens,
            "store": False,
            "stream": False,
            "tools": [],
        }
        if self._supports_temperature:
            payload["temperature"] = request.temperature
        data = bytearray()
        try:
            async with (
                httpx.AsyncClient(
                    transport=self._transport,
                    timeout=self._timeout,
                    follow_redirects=False,
                    trust_env=False,
                ) as client,
                client.stream(
                    "POST",
                    self._url,
                    json=payload,
                    headers={
                        "Authorization": "Bearer " + self._key.get_secret_value(),
                        "Accept": "application/json",
                    },
                ) as response,
            ):
                status = response.status_code
                if status in (401, 403):
                    raise IntegrationNotConfiguredError(
                        "OpenAI credentials or model access were rejected."
                    )
                if status == 429:
                    raise RateLimitExceededError("OpenAI request was rate limited.")
                if status >= 500:
                    raise IntegrationError("OpenAI service is temporarily unavailable.")
                if status != 200:
                    raise DomainValidationError("OpenAI request was rejected.")
                if (
                    response.headers.get("content-type", "").split(";")[0].strip().lower()
                    != "application/json"
                ):
                    raise IntegrationError("OpenAI returned an unsupported response format.")
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > self._max_response_bytes:
                        raise IntegrationError("OpenAI response exceeded the size limit.")
                    data.extend(chunk)
        except httpx.HTTPError:
            raise IntegrationError("OpenAI connection failed or timed out.") from None
        try:
            body = json.loads(data)
            if (
                not isinstance(body, dict)
                or body.get("status") != "completed"
                or body.get("error") is not None
            ):
                raise ValueError
            actual_model = body["model"]
            if (
                not isinstance(actual_model, str)
                or not actual_model.strip()
                or len(actual_model) > 200
            ):
                raise ValueError
            output = body["output"]
            if not isinstance(output, list):
                raise ValueError
            parts = []
            for item in output:
                if not isinstance(item, dict):
                    raise ValueError
                if item.get("type") == "reasoning":
                    continue
                if (
                    item.get("type") != "message"
                    or item.get("role") != "assistant"
                    or item.get("status") != "completed"
                    or not isinstance(item.get("content"), list)
                ):
                    raise ValueError
                for content in item["content"]:
                    if (
                        not isinstance(content, dict)
                        or content.get("type") != "output_text"
                        or not isinstance(content.get("text"), str)
                    ):
                        raise ValueError
                    parts.append(content["text"])
            text = "".join(parts)
            if not text.strip():
                raise ValueError
            usage = body["usage"]
            if not isinstance(usage, dict):
                raise ValueError
            counts = [usage["input_tokens"], usage["output_tokens"]]
            if any(type(count) is not int or not 0 <= count <= 1000000000 for count in counts):
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise IntegrationError(
                "OpenAI returned an incomplete, refused or invalid text response."
            ) from None
        return LLMResponse(
            text=text,
            provider=self.name,
            model=actual_model,
            input_tokens=counts[0],
            output_tokens=counts[1],
            finish_reason="stop",
            is_mock=False,
        )
