"""Property, project and recommendation schemas.

Listings always carry ``is_demo`` and ``data_as_of`` so the UI and agents can
disclose provenance; price/availability are never assumed current.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class PropertyType(StrEnum):
    APARTMENT = "apartment"
    VILLA = "villa"
    TOWNHOUSE = "townhouse"
    PENTHOUSE = "penthouse"
    OFFICE = "office"
    RETAIL = "retail"
    PLOT = "plot"


class CompletionStatus(StrEnum):
    OFF_PLAN = "off_plan"
    READY = "ready"


class Availability(StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    UNKNOWN = "unknown"


class PaymentPlanInfo(BaseModel):
    name: str
    down_payment_pct: Decimal = Field(ge=0, le=100)
    during_construction_pct: Decimal = Field(default=Decimal(0), ge=0, le=100)
    on_handover_pct: Decimal = Field(default=Decimal(0), ge=0, le=100)
    post_handover_pct: Decimal = Field(default=Decimal(0), ge=0, le=100)
    post_handover_months: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _sums_to_100(self) -> PaymentPlanInfo:
        total = (
            self.down_payment_pct
            + self.during_construction_pct
            + self.on_handover_pct
            + self.post_handover_pct
        )
        if total != Decimal(100):
            raise ValueError(f"payment plan percentages must sum to 100, got {total}")
        return self


class PropertyListing(BaseModel):
    listing_id: str
    project_name: str
    developer: str
    community: str
    city: str = "Dubai"
    property_type: PropertyType
    bedrooms: int = Field(ge=0)
    size_sqft: Decimal | None = Field(default=None, gt=0)
    price_aed: Decimal | None = Field(default=None, gt=0)
    availability: Availability = Availability.UNKNOWN
    completion_status: CompletionStatus
    handover_quarter: str | None = None  # e.g. "Q4 2027"
    payment_plan: PaymentPlanInfo | None = None
    source: str
    is_demo: bool = False
    data_as_of: date | None = None


class PropertySearchCriteria(BaseModel):
    budget_min_aed: Decimal | None = Field(default=None, ge=0)
    budget_max_aed: Decimal | None = Field(default=None, ge=0)
    locations: list[str] = Field(default_factory=list)
    property_types: list[PropertyType] = Field(default_factory=list)
    bedrooms_min: int | None = Field(default=None, ge=0)
    bedrooms_max: int | None = Field(default=None, ge=0)
    completion_status: CompletionStatus | None = None
    require_payment_plan: bool = False
    include_unavailable: bool = False
    limit: int = Field(default=5, ge=1, le=50)


class PropertyRecommendation(BaseModel):
    listing: PropertyListing
    score: float = Field(ge=0, le=1)
    reasons: list[str]
    caveats: list[str] = Field(default_factory=list)
