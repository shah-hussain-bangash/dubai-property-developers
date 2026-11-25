"""n8n adapter: triggers user-defined n8n webhook workflows (``{base}/webhook/{path}``)."""

from __future__ import annotations

import re
from typing import Any, Protocol

import httpx

from core.exceptions.errors import DomainValidationError
from integrations.base import HttpIntegrationClient, IntegrationConfig, NoAuth
from schemas.integrations.models import ApiAccessStatus, IntegrationDescriptor


def validated_webhook_path(value: object) -> str:
    """Keep a webhook name beneath /webhook/ without URL interpretation."""
    if isinstance(value, str) and len(value) <= 1024:
        # Preserve the adapter's existing support for outer slashes.
        path = value.strip("/")
        segments = path.split("/")
        if all(
            segment not in {"", ".", ".."} and re.fullmatch(r"[A-Za-z0-9_.-]+", segment) is not None
            for segment in segments
        ):
            return path
    raise DomainValidationError(
        "Webhook path must contain nonempty ASCII name segments without URL controls"
    )


class N8nConfig(IntegrationConfig):
    webhook_base_url: str | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.webhook_base_url)


class N8nClient(Protocol):
    async def trigger(
        self, webhook_path: str, payload: dict[str, Any], *, idempotency_key: str
    ) -> Any: ...


class MockN8nClient:
    def __init__(self) -> None:
        self.triggered: list[dict[str, Any]] = []

    async def trigger(
        self, webhook_path: str, payload: dict[str, Any], *, idempotency_key: str
    ) -> Any:
        webhook_path = validated_webhook_path(webhook_path)
        self.triggered.append({"path": webhook_path, "payload": payload, "key": idempotency_key})
        return {"accepted": True, "is_mock": True}


class HttpN8nClient:
    def __init__(
        self, config: N8nConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        assert config.webhook_base_url
        self._http = HttpIntegrationClient(
            integration="n8n",
            base_url=config.webhook_base_url.rstrip("/"),
            # Add header auth here if the n8n webhook node is configured for it.
            auth=NoAuth(),
            retry_policy=config.retry_policy(),
            transport=transport,
        )

    async def trigger(
        self, webhook_path: str, payload: dict[str, Any], *, idempotency_key: str
    ) -> Any:
        webhook_path = validated_webhook_path(webhook_path)
        return await self._http.request(
            "POST",
            f"/webhook/{webhook_path}",
            json=payload,
            idempotency_key=idempotency_key,
        )

    async def aclose(self) -> None:
        """Release the HTTP connection pool owned by this adapter."""
        await self._http.aclose()


def descriptor(config: N8nConfig) -> IntegrationDescriptor:
    return IntegrationDescriptor(
        name="n8n",
        display_name="n8n Automation",
        mode=config.mode,
        configured=config.is_configured,
        api_access=ApiAccessStatus.DOCUMENTED_API,
        notes="Triggers webhook workflows you define in your own n8n instance.",
    )
