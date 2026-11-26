"""EspoCRM adapter.

HTTP implementation follows EspoCRM's documented REST API (``/api/v1/{Entity}``,
``X-Api-Key`` auth for API users). It has not been tested against a live
instance; verify field names against your EspoCRM version before enabling LIVE.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from copy import deepcopy
from typing import Any, Protocol

import httpx
from pydantic import SecretStr

from core.exceptions.errors import ConflictError, DomainValidationError, NotFoundError
from integrations.base import ApiKeyHeaderAuth, HttpIntegrationClient, IntegrationConfig
from schemas.integrations.models import ApiAccessStatus, IntegrationDescriptor


def validate_crm_record_id(value: object) -> None:
    """Accept one bounded, literal path segment; never normalize a record ID."""
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) is None:
        raise DomainValidationError(
            "CRM record ID must be 1-128 ASCII letters, digits, underscores or hyphens"
        )


def validate_crm_lead_fields(value: object) -> dict[str, Any]:
    """Lead fields cannot supply or replace the provider-owned record identity."""
    if not isinstance(value, dict):
        raise DomainValidationError("CRM lead data must be an object")
    if "id" in value:
        raise DomainValidationError("CRM record ID is read-only")
    return value


def created_record_id(body: Any) -> str:
    """Accept a provider acknowledgement without coercing its record identity."""
    identifier = body.get("id") if isinstance(body, dict) else None
    if not isinstance(identifier, str):
        raise DomainValidationError("CRM creation response requires a string record ID")
    validate_crm_record_id(identifier)
    return identifier


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
    """In-memory CRM with detached input/output records, like HTTP JSON payloads."""

    def __init__(self) -> None:
        self.leads: dict[str, dict[str, Any]] = {}
        self.notes: list[dict[str, Any]] = []
        self._ids = itertools.count(1)
        self._idempotency: dict[str, str] = {}
        self._creation_fingerprints: dict[str, str] = {}

    async def find_leads(self, *, email: str | None, phone: str | None) -> list[dict[str, Any]]:
        return [
            deepcopy(lead)
            for lead in self.leads.values()
            if (email and lead.get("emailAddress") == email)
            or (phone and lead.get("phoneNumber") == phone)
        ]

    async def get_lead(self, external_id: str) -> dict[str, Any]:
        validate_crm_record_id(external_id)
        try:
            return deepcopy(self.leads[external_id])
        except KeyError as exc:
            raise NotFoundError(f"mock CRM lead {external_id} not found") from exc

    async def create_lead(self, data: dict[str, Any], *, idempotency_key: str) -> str:
        validate_crm_lead_fields(data)
        try:
            canonical = json.dumps(
                data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            )
            fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        except (TypeError, ValueError, OverflowError, UnicodeError) as exc:
            raise DomainValidationError("CRM creation data must contain only valid JSON") from exc
        if idempotency_key in self._idempotency:
            if self._creation_fingerprints.get(idempotency_key) != fingerprint:
                raise ConflictError("CRM retry key was already used with different creation data")
            return self._idempotency[idempotency_key]
        external_id = f"mock-lead-{next(self._ids):05d}"
        self.leads[external_id] = {"id": external_id, **deepcopy(data)}
        self._idempotency[idempotency_key] = external_id
        self._creation_fingerprints[idempotency_key] = fingerprint
        return external_id

    async def update_lead(self, external_id: str, data: dict[str, Any]) -> None:
        validate_crm_record_id(external_id)
        validate_crm_lead_fields(data)
        if external_id not in self.leads:
            raise NotFoundError(f"mock CRM lead {external_id} not found")
        self.leads[external_id].update(deepcopy(data))

    async def add_note(self, *, parent_type: str, parent_id: str, text: str) -> str:
        note_id = f"mock-note-{next(self._ids):05d}"
        self.notes.append(
            {"id": note_id, "parentType": parent_type, "parentId": parent_id, "post": text}
        )
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
        validate_crm_record_id(external_id)
        return await self._http.request("GET", f"/Lead/{external_id}")  # type: ignore[no-any-return]

    async def create_lead(self, data: dict[str, Any], *, idempotency_key: str) -> str:
        validate_crm_lead_fields(data)
        body = await self._http.request("POST", "/Lead", json=data, idempotency_key=idempotency_key)
        return created_record_id(body)

    async def update_lead(self, external_id: str, data: dict[str, Any]) -> None:
        validate_crm_record_id(external_id)
        validate_crm_lead_fields(data)
        await self._http.request("PUT", f"/Lead/{external_id}", json=data)

    async def add_note(self, *, parent_type: str, parent_id: str, text: str) -> str:
        body = await self._http.request(
            "POST",
            "/Note",
            json={"type": "Post", "parentType": parent_type, "parentId": parent_id, "post": text},
        )
        return created_record_id(body)

    async def aclose(self) -> None:
        """Release the HTTP connection pool owned by this adapter."""
        await self._http.aclose()


def descriptor(config: EspoCRMConfig) -> IntegrationDescriptor:
    return IntegrationDescriptor(
        name="espocrm",
        display_name="EspoCRM",
        mode=config.mode,
        configured=config.is_configured,
        api_access=ApiAccessStatus.DOCUMENTED_API,
        notes="HTTP adapter written to public REST docs; untested against a live instance.",
    )
