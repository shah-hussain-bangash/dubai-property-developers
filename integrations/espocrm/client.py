"""EspoCRM adapter.

HTTP implementation follows EspoCRM's documented REST API (``/api/v1/{Entity}``,
``X-Api-Key`` auth for API users). It has not been tested against a live
instance; verify field names against your EspoCRM version before enabling LIVE.
"""

from __future__ import annotations

import itertools
from typing import Any, Protocol

import httpx
from pydantic import SecretStr

from core.exceptions.errors import NotFoundError
from integrations.base import ApiKeyHeaderAuth, HttpIntegrationClient, IntegrationConfig
from schemas.integrations.models import ApiAccessStatus, IntegrationDescriptor


class EspoCRMConfig(IntegrationConfig):
    base_url: str | None = None
    api_key: SecretStr | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)


class CRMClient(Protocol):
    async def find_leads(self, *, email: str | None, phone: str | None) -> list[dict[str, Any]]: ...

    async def get_lead(self, external_id: str) -> dict[str, Any]: ...

    async def create_lead(self, data: dict[str, Any], *, idempotency_key: str) -> str: ...

    async def update_lead(self, external_id: str, data: dict[str, Any]) -> None: ...

    async def add_note(self, *, parent_type: str, parent_id: str, text: str) -> str: ...


class MockEspoCRMClient:
    """In-memory CRM with EspoCRM-shaped records (``emailAddress``, ``phoneNumber``)."""

    def __init__(self) -> None:
        self.leads: dict[str, dict[str, Any]] = {}
        self.notes: list[dict[str, Any]] = []
        self._ids = itertools.count(1)
        self._idempotency: dict[str, str] = {}

    async def find_leads(self, *, email: str | None, phone: str | None) -> list[dict[str, Any]]:
        return [
            lead
            for lead in self.leads.values()
            if (email and lead.get("emailAddress") == email)
            or (phone and lead.get("phoneNumber") == phone)
        ]

    async def get_lead(self, external_id: str) -> dict[str, Any]:
        try:
            return dict(self.leads[external_id])
        except KeyError as exc:
            raise NotFoundError(f"mock CRM lead {external_id} not found") from exc

    async def create_lead(self, data: dict[str, Any], *, idempotency_key: str) -> str:
        if idempotency_key in self._idempotency:
            return self._idempotency[idempotency_key]
        external_id = f"mock-lead-{next(self._ids):05d}"
        self.leads[external_id] = {"id": external_id, **data}
        self._idempotency[idempotency_key] = external_id
        return external_id

    async def update_lead(self, external_id: str, data: dict[str, Any]) -> None:
        if external_id not in self.leads:
            raise NotFoundError(f"mock CRM lead {external_id} not found")
        self.leads[external_id].update(data)

    async def add_note(self, *, parent_type: str, parent_id: str, text: str) -> str:
        note_id = f"mock-note-{next(self._ids):05d}"
        self.notes.append({"id": note_id, "parentType": parent_type, "parentId": parent_id, "post": text})
        return note_id


class HttpEspoCRMClient:
    def __init__(self, config: EspoCRMConfig, *, transport: httpx.AsyncBaseTransport | None = None):
        assert config.api_key is not None and config.base_url
        self._http = HttpIntegrationClient(
            integration="espocrm",
            base_url=config.base_url.rstrip("/") + "/api/v1",
            auth=ApiKeyHeaderAuth("X-Api-Key", config.api_key),
            retry_policy=config.retry_policy(),
            transport=transport,
        )

    async def find_leads(self, *, email: str | None, phone: str | None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for attribute, value in (("emailAddress", email), ("phoneNumber", phone)):
            if not value:
                continue
            params = {
                "where[0][type]": "equals",
                "where[0][attribute]": attribute,
                "where[0][value]": value,
                "maxSize": 20,
            }
            body = await self._http.request("GET", "/Lead", params=params)
            results.extend((body or {}).get("list", []))
        return list({r["id"]: r for r in results}.values())

    async def get_lead(self, external_id: str) -> dict[str, Any]:
        return await self._http.request("GET", f"/Lead/{external_id}")  # type: ignore[no-any-return]

    async def create_lead(self, data: dict[str, Any], *, idempotency_key: str) -> str:
        body = await self._http.request("POST", "/Lead", json=data, idempotency_key=idempotency_key)
        return str(body["id"])

    async def update_lead(self, external_id: str, data: dict[str, Any]) -> None:
        await self._http.request("PUT", f"/Lead/{external_id}", json=data)

    async def add_note(self, *, parent_type: str, parent_id: str, text: str) -> str:
        body = await self._http.request(
            "POST",
            "/Note",
            json={"type": "Post", "parentType": parent_type, "parentId": parent_id, "post": text},
        )
        return str(body["id"])


def descriptor(config: EspoCRMConfig) -> IntegrationDescriptor:
    return IntegrationDescriptor(
        name="espocrm",
        display_name="EspoCRM",
        mode=config.mode,
        configured=config.is_configured,
        api_access=ApiAccessStatus.DOCUMENTED_API,
        notes="HTTP adapter written to public REST docs; untested against a live instance.",
    )
