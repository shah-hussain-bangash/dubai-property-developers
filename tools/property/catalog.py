"""Property catalog contract. The in-memory catalog serves the fictional demo set."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from database.seeds.demo_catalog import DEMO_LISTINGS
from schemas.properties.models import PropertyListing


class PropertyCatalog(Protocol):
    async def all_listings(self) -> list[PropertyListing]: ...

    async def get(self, listing_id: str) -> PropertyListing | None: ...


class InMemoryPropertyCatalog:
    def __init__(self, listings: Iterable[PropertyListing] = DEMO_LISTINGS) -> None:
        self._listings = {listing.listing_id: listing for listing in listings}

    async def all_listings(self) -> list[PropertyListing]:
        return list(self._listings.values())

    async def get(self, listing_id: str) -> PropertyListing | None:
        return self._listings.get(listing_id)
