from __future__ import annotations

from decimal import Decimal

from agents.lead_intake.normalization import dedupe_keys, normalize_phone
from database.seeds.demo_catalog import DEMO_LISTINGS
from schemas.leads.models import QualificationCategory
from schemas.properties.models import Availability, PropertySearchCriteria, PropertyType
from tests.factories import normalized_lead
from tools.analytics.lead_scoring import score_lead
from tools.property.matching import match_properties


def test_phone_normalization_uae_local_and_international() -> None:
    assert normalize_phone("050 000 0001") == ("+971500000001", "AE")
    assert normalize_phone("+971 50 000 0001")[0] == "+971500000001"
    assert normalize_phone("not a phone") == (None, None)
    assert normalize_phone(None) == (None, None)


def test_dedupe_keys_do_not_contain_raw_pii() -> None:
    keys = dedupe_keys("demo@example.com", "+971500000001")
    assert len(keys) == 2
    assert all("example.com" not in k and "971500" not in k for k in keys)


def test_hot_lead_scoring_is_explainable() -> None:
    lead = normalized_lead(message="Please book a viewing")
    score = score_lead(lead)
    assert score.category == QualificationCategory.HOT
    assert score.score == sum(f.points for f in score.factors)
    assert {f.name for f in score.factors} >= {"timeline", "budget_stated", "explicit_intent"}


def test_sparse_lead_is_cold_and_rent_goes_to_nurture() -> None:
    sparse = normalized_lead(
        phone_e164=None,
        budget_max_aed=None,
        preferred_locations=[],
        property_types=[],
        bedrooms=None,
        purpose="unknown",
        timeline_months=None,
    )
    assert score_lead(sparse).category == QualificationCategory.COLD
    assert score_lead(normalized_lead(purpose="rent")).category == QualificationCategory.NURTURE


def test_matching_respects_hard_filters_and_flags_demo() -> None:
    criteria = PropertySearchCriteria(
        budget_max_aed=Decimal(1_500_000),
        locations=["Business Bay"],
        property_types=[PropertyType.APARTMENT],
    )
    recs = match_properties(list(DEMO_LISTINGS), criteria)
    assert [r.listing.listing_id for r in recs] == ["DEMO-003"]
    rec = recs[0]
    assert any("DEMO DATA" in c for c in rec.caveats)
    assert any("guaranteed" in c for c in rec.caveats)


def test_matching_excludes_sold_and_reserved_by_default() -> None:
    recs = match_properties(list(DEMO_LISTINGS), PropertySearchCriteria(limit=50))
    assert all(
        r.listing.availability not in {Availability.SOLD, Availability.RESERVED} for r in recs
    )


def test_unconfirmed_price_is_caveated_not_invented() -> None:
    recs = match_properties(
        list(DEMO_LISTINGS), PropertySearchCriteria(property_types=[PropertyType.TOWNHOUSE])
    )
    assert recs[0].listing.price_aed is None
    assert any("Price not confirmed" in c for c in recs[0].caveats)
