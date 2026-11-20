"""Property Finder adapter - documented interface only, pending authorized API access."""

from __future__ import annotations

from integrations.listing_portal import (
    ListingPortalClient,
    ListingPortalConfig,
    MockListingPortalClient,
    PendingAccessListingPortalClient,
)
from schemas.integrations.models import ApiAccessStatus, IntegrationDescriptor

PORTAL = "propertyfinder"


class PropertyFinderConfig(ListingPortalConfig):
    pass


def build_client(config: PropertyFinderConfig) -> ListingPortalClient:
    if config.mode == "mock":
        return MockListingPortalClient(PORTAL)
    return PendingAccessListingPortalClient(PORTAL)


def descriptor(config: PropertyFinderConfig) -> IntegrationDescriptor:
    return IntegrationDescriptor(
        name=PORTAL,
        display_name="Property Finder",
        mode=config.mode,
        configured=config.is_configured,
        api_access=ApiAccessStatus.PENDING_AUTHORIZED_ACCESS,
        notes="Interface only. Requires authorized partner API access; no scraping.",
    )
