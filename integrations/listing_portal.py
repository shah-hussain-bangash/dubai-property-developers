"""Shared contract for property listing portals (Bayut, Property Finder).

No scraping. Live adapters are deliberately not implemented: they require
authorized partner/API access and the provider's official documentation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from core.exceptions.errors import IntegrationNotConfiguredError
from integrations.base import IntegrationConfig


class ListingPortalConfig(IntegrationConfig):
    partner_id: str | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.partner_id)


class ListingPortalClient(Protocol):
    async def fetch_leads(self, *, since: datetime) -> list[dict[str, Any]]: ...

    async def fetch_listing_status(self, reference: str) -> dict[str, Any]: ...


class MockListingPortalClient:
    def __init__(self, portal: str, leads: list[dict[str, Any]] | None = None) -> None:
        self.portal = portal
        self._leads = leads or []

    async def fetch_leads(self, *, since: datetime) -> list[dict[str, Any]]:
        return [lead for lead in self._leads if lead.get("received_at", since) >= since]

    async def fetch_listing_status(self, reference: str) -> dict[str, Any]:
        return {"reference": reference, "portal": self.portal, "status": "unknown", "is_mock": True}


class PendingAccessListingPortalClient:
    def __init__(self, portal: str) -> None:
        self.portal = portal

    async def fetch_leads(self, *, since: datetime) -> list[dict[str, Any]]:
        raise IntegrationNotConfiguredError(f"{self.portal}: pending authorized API access")

    async def fetch_listing_status(self, reference: str) -> dict[str, Any]:
        raise IntegrationNotConfiguredError(f"{self.portal}: pending authorized API access")
