"""Slack adapter for internal staff notifications (incoming webhook)."""

from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from integrations.base import HttpIntegrationClient, IntegrationConfig, NoAuth
from schemas.integrations.models import ApiAccessStatus, IntegrationDescriptor


class SlackConfig(IntegrationConfig):
    webhook_url: SecretStr | None = None  # the URL itself is the credential

    @property
    def is_configured(self) -> bool:
        return self.webhook_url is not None


class SlackNotifier(Protocol):
    async def notify(self, text: str, *, idempotency_key: str) -> None: ...


class MockSlackNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def notify(self, text: str, *, idempotency_key: str) -> None:
        self.messages.append(text)


class WebhookSlackNotifier:
    def __init__(
        self, config: SlackConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        assert config.webhook_url is not None
        parts = urlsplit(config.webhook_url.get_secret_value())
        self._path = parts.path
        self._http = HttpIntegrationClient(
            integration="slack",
            base_url=f"{parts.scheme}://{parts.netloc}",
            auth=NoAuth(),
            retry_policy=config.retry_policy(),
            transport=transport,
        )

    async def notify(self, text: str, *, idempotency_key: str) -> None:
        payload: dict[str, Any] = {"text": text}
        await self._http.request("POST", self._path, json=payload, expect_json=False)


def descriptor(config: SlackConfig) -> IntegrationDescriptor:
    return IntegrationDescriptor(
        name="slack",
        display_name="Slack",
        mode=config.mode,
        configured=config.is_configured,
        api_access=ApiAccessStatus.DOCUMENTED_API,
        notes="Internal staff alerts only (escalations, approvals). Never customer data beyond IDs.",
    )
