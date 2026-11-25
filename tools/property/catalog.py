"""Property catalog contract. The in-memory catalog serves the fictional demo set."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from database.seeds.demo_catalog import DEMO_LISTINGS
from schemas.properties.models import PropertyListing


class PropertyCatalog(Protocol):
    """Read-only listing snapshots; edits to returned models do not update inventory."""

    async def all_listings(self) -> list[PropertyListing]: ...

    async def get(self, listing_id: str) -> PropertyListing | None: ...


class InMemoryPropertyCatalog:
    def __init__(self, listings: Iterable[PropertyListing] = DEMO_LISTINGS) -> None:
        self._listings = {listing.listing_id: listing.model_copy(deep=True) for listing in listings}

    async def all_listings(self) -> list[PropertyListing]:
        return [listing.model_copy(deep=True) for listing in self._listings.values()]

    async def get(self, listing_id: str) -> PropertyListing | None:
        listing = self._listings.get(listing_id)
        return listing.model_copy(deep=True) if listing is not None else None
