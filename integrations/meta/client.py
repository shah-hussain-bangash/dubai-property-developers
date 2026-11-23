"""Meta WhatsApp Business (Cloud API) adapter.

The HTTP client targets the documented ``POST /{version}/{phone-number-id}/messages``
endpoint. Business rules (24h customer-service window, opt-in, approved
templates) are enforced in ``tools/whatsapp`` before this client is called.
Untested against a live WhatsApp Business account.
"""

from __future__ import annotations

import itertools
from typing import Any, Protocol

import httpx
from pydantic import SecretStr

from integrations.base import BearerTokenAuth, HttpIntegrationClient, IntegrationConfig
from schemas.integrations.models import ApiAccessStatus, IntegrationDescriptor

GRAPH_BASE_URL = "https://graph.facebook.com"


class MetaWhatsAppConfig(IntegrationConfig):
    phone_number_id: str | None = None
    access_token: SecretStr | None = None
    app_secret: SecretStr | None = None  # for webhook X-Hub-Signature-256 verification
    api_version: str = "v20.0"

    @property
    def is_configured(self) -> bool:
        return bool(self.phone_number_id and self.access_token)


class WhatsAppClient(Protocol):
    async def send_text(self, *, to_e164: str, body: str, idempotency_key: str) -> str: ...

    async def send_template(
        self,
        *,
        to_e164: str,
        template_name: str,
        language_code: str,
        components: list[dict[str, Any]],
        idempotency_key: str,
    ) -> str: ...


class MockWhatsAppClient:
    def __init__(self) -> None:
        self.outbox: list[dict[str, Any]] = []
        self._ids = itertools.count(1)
        self._seen: dict[str, str] = {}

    def _record(self, idempotency_key: str, message: dict[str, Any]) -> str:
        if idempotency_key in self._seen:
            return self._seen[idempotency_key]
        message_id = f"mock-wamid-{next(self._ids):05d}"
        self.outbox.append({"id": message_id, **message})
        self._seen[idempotency_key] = message_id
        return message_id

    async def send_text(self, *, to_e164: str, body: str, idempotency_key: str) -> str:
        return self._record(idempotency_key, {"to": to_e164, "type": "text", "body": body})

    async def send_template(
        self,
        *,
        to_e164: str,
        template_name: str,
        language_code: str,
        components: list[dict[str, Any]],
        idempotency_key: str,
    ) -> str:
        return self._record(
            idempotency_key,
            {
                "to": to_e164,
                "type": "template",
                "template": template_name,
                "language": language_code,
            },
        )


class HttpWhatsAppClient:
    def __init__(
        self, config: MetaWhatsAppConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        assert config.access_token is not None and config.phone_number_id
        self._path = f"/{config.api_version}/{config.phone_number_id}/messages"
        self._http = HttpIntegrationClient(
            integration="meta_whatsapp",
            base_url=GRAPH_BASE_URL,
            auth=BearerTokenAuth(config.access_token),
            retry_policy=config.retry_policy(),
            transport=transport,
        )

    async def _post(self, payload: dict[str, Any], idempotency_key: str) -> str:
        body = await self._http.request(
            "POST", self._path, json=payload, idempotency_key=idempotency_key
        )
        return str(body["messages"][0]["id"])

    async def send_text(self, *, to_e164: str, body: str, idempotency_key: str) -> str:
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "to": to_e164.lstrip("+"),
                "type": "text",
                "text": {"body": body},
            },
            idempotency_key,
        )

    async def send_template(
        self,
        *,
        to_e164: str,
        template_name: str,
        language_code: str,
        components: list[dict[str, Any]],
        idempotency_key: str,
    ) -> str:
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "to": to_e164.lstrip("+"),
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language_code},
                    "components": components,
                },
            },
            idempotency_key,
        )

    async def aclose(self) -> None:
        """Release the HTTP connection pool owned by this adapter."""
        await self._http.aclose()


def descriptor(config: MetaWhatsAppConfig) -> IntegrationDescriptor:
    return IntegrationDescriptor(
        name="meta_whatsapp",
        display_name="Meta WhatsApp Business",
        mode=config.mode,
        configured=config.is_configured,
        api_access=ApiAccessStatus.DOCUMENTED_API,
        notes="Cloud API adapter; requires a verified WhatsApp Business account and approved templates.",
    )
