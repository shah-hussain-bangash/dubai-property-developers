"""Bayut adapter - documented interface only, pending authorized API access."""

from __future__ import annotations

from integrations.listing_portal import (
    ListingPortalClient,
    ListingPortalConfig,
    MockListingPortalClient,
    PendingAccessListingPortalClient,
)
from schemas.integrations.models import ApiAccessStatus, IntegrationDescriptor

PORTAL = "bayut"


class BayutConfig(ListingPortalConfig):
    pass


def build_client(config: BayutConfig) -> ListingPortalClient:
    if config.mode == "mock":
        return MockListingPortalClient(PORTAL)
    return PendingAccessListingPortalClient(PORTAL)


def descriptor(config: BayutConfig) -> IntegrationDescriptor:
    return IntegrationDescriptor(
        name=PORTAL,
        display_name="Bayut",
        mode=config.mode,
        configured=config.is_configured,
        api_access=ApiAccessStatus.PENDING_AUTHORIZED_ACCESS,
        notes="Interface only. Requires an authorized partner API agreement; no scraping.",
    )
