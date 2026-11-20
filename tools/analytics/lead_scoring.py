"""Rules-based, explainable lead scoring (``rules-v1``).

Every point awarded is recorded as a ``ScoreFactor`` so sales staff can see why
a lead was ranked. Weights are a starting point to be calibrated on real
conversion data; they are not derived from any dataset.
"""

from __future__ import annotations

from decimal import Decimal

from schemas.leads.models import (
    LeadPurpose,
    LeadScore,
    LeadSource,
    NormalizedLead,
    QualificationCategory,
    ScoreFactor,
)

MODEL_VERSION = "rules-v1"
_INTENT_KEYWORDS = ("viewing", "visit", "call me", "meeting", "book", "ready to buy", "reserve")


def score_lead(lead: NormalizedLead) -> LeadScore:
    factors: list[ScoreFactor] = []

    def add(name: str, points: int, reason: str) -> None:
        factors.append(ScoreFactor(name=name, points=points, reason=reason))

    if lead.email and lead.phone_e164:
        add("contactability", 10, "Both email and phone provided")
    elif lead.phone_e164:
        add("contactability", 6, "Phone provided")
    else:
        add("contactability", 4, "Email only")

    if lead.budget_max_aed is not None:
        add("budget_stated", 15, "Budget provided")
        if lead.budget_max_aed >= Decimal(500_000):
            add("budget_realistic", 5, "Budget within typical Dubai sales range")

    if lead.timeline_months is not None:
        if lead.timeline_months <= 3:
            add("timeline", 25, "Intends to transact within 3 months")
        elif lead.timeline_months <= 6:
            add("timeline", 15, "Intends to transact within 6 months")
        elif lead.timeline_months <= 12:
            add("timeline", 8, "Intends to transact within 12 months")
        else:
            add("timeline", 2, "Long timeline (>12 months)")

    if lead.purpose in {LeadPurpose.INVESTMENT, LeadPurpose.END_USE}:
        add("purpose_known", 10, f"Purpose stated: {lead.purpose.value}")
    elif lead.purpose == LeadPurpose.RENT:
        add("purpose_rent", 0, "Rental enquiry - route to leasing, not sales")

    if lead.preferred_locations:
        add("location_pref", 10, "Preferred locations specified")
    if lead.property_types:
        add("type_pref", 5, "Property type specified")
    if lead.bedrooms is not None:
        add("bedrooms_pref", 5, "Bedroom count specified")

    message = (lead.message or "").lower()
    if any(k in message for k in _INTENT_KEYWORDS):
        add("explicit_intent", 10, "Message requests a viewing, call or meeting")

    source_points = {LeadSource.REFERRAL: 10, LeadSource.BAYUT: 5, LeadSource.PROPERTY_FINDER: 5}
    if lead.source in source_points:
        add("source", source_points[lead.source], f"Source: {lead.source.value}")

    score = max(0, min(100, sum(f.points for f in factors)))
    if lead.purpose == LeadPurpose.RENT:
        category = QualificationCategory.NURTURE
    elif score >= 70:
        category = QualificationCategory.HOT
    elif score >= 45:
        category = QualificationCategory.WARM
    elif score >= 20:
        category = QualificationCategory.NURTURE
    else:
        category = QualificationCategory.COLD
    return LeadScore(score=score, category=category, factors=factors, model_version=MODEL_VERSION)
