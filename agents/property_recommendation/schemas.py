from __future__ import annotations

from pydantic import BaseModel

from schemas.properties.models import PropertyRecommendation, PropertySearchCriteria

DISCLAIMER = (
    "Recommendations are based on catalog data as of the date shown. Prices, availability, "
    "payment plans and handover dates must be confirmed with the developer before quoting. "
    "No investment return is implied or guaranteed."
)


class RecommendationInput(BaseModel):
    criteria: PropertySearchCriteria


class RecommendationOutput(BaseModel):
    recommendations: list[PropertyRecommendation]
    disclaimer: str = DISCLAIMER
    contains_demo_data: bool
    no_match_reason: str | None = None
