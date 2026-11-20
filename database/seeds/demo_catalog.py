"""Clearly fictional demo catalog for local development and tests.

Project and developer names are invented. Community names are real Dubai areas
used only as location labels. Prices are illustrative placeholders, NOT market
data, and every record is flagged ``is_demo=True``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from schemas.properties.models import (
    Availability,
    CompletionStatus,
    PaymentPlanInfo,
    PropertyListing,
    PropertyType,
)

DEMO_AS_OF = date(2026, 1, 1)
DEMO_SOURCE = "demo-seed"

_PLAN_60_40 = PaymentPlanInfo(
    name="Demo 60/40",
    down_payment_pct=Decimal(20),
    during_construction_pct=Decimal(40),
    on_handover_pct=Decimal(40),
)
_PLAN_POST_HANDOVER = PaymentPlanInfo(
    name="Demo Post-Handover",
    down_payment_pct=Decimal(10),
    during_construction_pct=Decimal(40),
    on_handover_pct=Decimal(10),
    post_handover_pct=Decimal(40),
    post_handover_months=36,
)


def _listing(listing_id: str, **values: object) -> PropertyListing:
    return PropertyListing(
        listing_id=listing_id,
        source=DEMO_SOURCE,
        is_demo=True,
        data_as_of=DEMO_AS_OF,
        **values,
    )


DEMO_LISTINGS: tuple[PropertyListing, ...] = (
    _listing(
        "DEMO-001",
        project_name="Demo Marina Residences (Fictional)",
        developer="Demo Developer Alpha (Fictional)",
        community="Dubai Marina",
        property_type=PropertyType.APARTMENT,
        bedrooms=1,
        size_sqft=Decimal(780),
        price_aed=Decimal(1_450_000),
        availability=Availability.AVAILABLE,
        completion_status=CompletionStatus.READY,
    ),
    _listing(
        "DEMO-002",
        project_name="Demo Marina Residences (Fictional)",
        developer="Demo Developer Alpha (Fictional)",
        community="Dubai Marina",
        property_type=PropertyType.APARTMENT,
        bedrooms=2,
        size_sqft=Decimal(1_220),
        price_aed=Decimal(2_300_000),
        availability=Availability.AVAILABLE,
        completion_status=CompletionStatus.READY,
    ),
    _listing(
        "DEMO-003",
        project_name="Demo Creek Heights (Fictional)",
        developer="Demo Developer Beta (Fictional)",
        community="Business Bay",
        property_type=PropertyType.APARTMENT,
        bedrooms=1,
        size_sqft=Decimal(720),
        price_aed=Decimal(1_250_000),
        availability=Availability.AVAILABLE,
        completion_status=CompletionStatus.OFF_PLAN,
        handover_quarter="Q4 2028",
        payment_plan=_PLAN_POST_HANDOVER,
    ),
    _listing(
        "DEMO-004",
        project_name="Demo Creek Heights (Fictional)",
        developer="Demo Developer Beta (Fictional)",
        community="Business Bay",
        property_type=PropertyType.PENTHOUSE,
        bedrooms=4,
        size_sqft=Decimal(4_100),
        price_aed=Decimal(9_800_000),
        availability=Availability.RESERVED,
        completion_status=CompletionStatus.OFF_PLAN,
        handover_quarter="Q4 2028",
        payment_plan=_PLAN_60_40,
    ),
    _listing(
        "DEMO-005",
        project_name="Demo Hills Villas (Fictional)",
        developer="Demo Developer Gamma (Fictional)",
        community="Dubai Hills Estate",
        property_type=PropertyType.VILLA,
        bedrooms=4,
        size_sqft=Decimal(3_600),
        price_aed=Decimal(6_900_000),
        availability=Availability.AVAILABLE,
        completion_status=CompletionStatus.OFF_PLAN,
        handover_quarter="Q2 2028",
        payment_plan=_PLAN_60_40,
    ),
    _listing(
        "DEMO-006",
        project_name="Demo Circle Gardens (Fictional)",
        developer="Demo Developer Delta (Fictional)",
        community="Jumeirah Village Circle",
        property_type=PropertyType.APARTMENT,
        bedrooms=0,
        size_sqft=Decimal(430),
        price_aed=Decimal(690_000),
        availability=Availability.AVAILABLE,
        completion_status=CompletionStatus.OFF_PLAN,
        handover_quarter="Q1 2028",
        payment_plan=_PLAN_POST_HANDOVER,
    ),
    _listing(
        "DEMO-007",
        project_name="Demo Circle Gardens (Fictional)",
        developer="Demo Developer Delta (Fictional)",
        community="Jumeirah Village Circle",
        property_type=PropertyType.TOWNHOUSE,
        bedrooms=3,
        size_sqft=Decimal(2_050),
        price_aed=None,  # price not confirmed: agents must say so rather than guess
        availability=Availability.UNKNOWN,
        completion_status=CompletionStatus.OFF_PLAN,
        handover_quarter="Q1 2028",
    ),
    _listing(
        "DEMO-008",
        project_name="Demo Downtown Lofts (Fictional)",
        developer="Demo Developer Alpha (Fictional)",
        community="Downtown Dubai",
        property_type=PropertyType.APARTMENT,
        bedrooms=2,
        size_sqft=Decimal(1_350),
        price_aed=Decimal(3_400_000),
        availability=Availability.SOLD,
        completion_status=CompletionStatus.READY,
    ),
)
