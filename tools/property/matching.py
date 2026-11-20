"""Deterministic, explainable property matching.

Hard filters remove ineligible listings; soft scores rank the rest. Every result
carries human-readable reasons and caveats. No prices or returns are inferred.
"""

from __future__ import annotations

from decimal import Decimal

from schemas.properties.models import (
    Availability,
    CompletionStatus,
    PropertyListing,
    PropertyRecommendation,
    PropertySearchCriteria,
)

WEIGHTS = {"budget": 0.35, "location": 0.25, "bedrooms": 0.2, "availability": 0.1, "plan": 0.1}
UNAVAILABLE = {Availability.SOLD, Availability.RESERVED}


def _location_match(listing: PropertyListing, locations: list[str]) -> bool:
    community = listing.community.lower()
    return any(loc.lower() in community or community in loc.lower() for loc in locations)


def is_eligible(listing: PropertyListing, c: PropertySearchCriteria) -> bool:
    if not c.include_unavailable and listing.availability in UNAVAILABLE:
        return False
    if c.property_types and listing.property_type not in c.property_types:
        return False
    if c.bedrooms_min is not None and listing.bedrooms < c.bedrooms_min:
        return False
    if c.bedrooms_max is not None and listing.bedrooms > c.bedrooms_max:
        return False
    if c.completion_status and listing.completion_status != c.completion_status:
        return False
    if c.require_payment_plan and listing.payment_plan is None:
        return False
    if c.locations and not _location_match(listing, c.locations):
        return False
    if listing.price_aed is not None:
        if c.budget_max_aed is not None and listing.price_aed > c.budget_max_aed:
            return False
        if c.budget_min_aed is not None and listing.price_aed < c.budget_min_aed * Decimal("0.8"):
            return False
    return True


def score_listing(listing: PropertyListing, c: PropertySearchCriteria) -> PropertyRecommendation:
    reasons: list[str] = []
    caveats: list[str] = []
    parts: dict[str, float] = {}

    if listing.price_aed is None:
        parts["budget"] = 0.4
        caveats.append("Price not confirmed; must be verified before discussing with the customer.")
    elif c.budget_max_aed:
        ratio = float(listing.price_aed / c.budget_max_aed)
        parts["budget"] = max(0.0, 1.0 - abs(0.85 - ratio))
        reasons.append(f"Listed at AED {listing.price_aed:,.0f}, within the stated budget.")
    else:
        parts["budget"] = 0.6

    if c.locations:
        parts["location"] = 1.0
        reasons.append(f"Located in {listing.community}, a preferred area.")
    else:
        parts["location"] = 0.6

    wanted = c.bedrooms_min if c.bedrooms_min == c.bedrooms_max else None
    parts["bedrooms"] = 1.0 if wanted is None or listing.bedrooms == wanted else 0.7
    reasons.append(f"{listing.bedrooms}-bedroom {listing.property_type.value}.")

    if listing.availability == Availability.AVAILABLE:
        parts["availability"] = 1.0
    else:
        parts["availability"] = 0.5
        caveats.append(f"Availability is '{listing.availability.value}'; confirm before offering.")

    if listing.payment_plan is not None:
        parts["plan"] = 1.0
        reasons.append(f"Payment plan available: {listing.payment_plan.name}.")
    else:
        parts["plan"] = 0.5 if listing.completion_status == CompletionStatus.OFF_PLAN else 0.7

    if listing.completion_status == CompletionStatus.OFF_PLAN:
        caveats.append(
            f"Off-plan; handover {listing.handover_quarter or 'date not confirmed'} is subject to the developer."
        )
    if listing.is_demo:
        caveats.append("DEMO DATA: fictional listing for development only.")
    caveats.append("No investment return is implied or guaranteed.")

    score = sum(WEIGHTS[k] * v for k, v in parts.items())
    return PropertyRecommendation(listing=listing, score=round(min(score, 1.0), 4), reasons=reasons, caveats=caveats)


def match_properties(
    listings: list[PropertyListing], criteria: PropertySearchCriteria
) -> list[PropertyRecommendation]:
    ranked = [score_listing(lst, criteria) for lst in listings if is_eligible(lst, criteria)]
    ranked.sort(key=lambda r: (-r.score, r.listing.listing_id))
    return ranked[: criteria.limit]
