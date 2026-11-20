"""Fictional test data builders (example.com emails, +971 50 000 xxxx numbers)."""

from __future__ import annotations

import os
from typing import Any

from schemas.leads.models import LeadSubmission, NormalizedLead

TENANT = "demo-org"


def lead_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "full_name": "Demo Lead One",
        "email": "demo.lead.one@example.com",
        "phone": "050 000 0001",
        "source": "website",
        "message": "Looking for a 1 bedroom apartment in Business Bay, would like a viewing.",
        "budget_min_aed": "900000",
        "budget_max_aed": "1500000",
        "preferred_locations": ["business bay"],
        "property_types": ["apartment"],
        "bedrooms": 1,
        "purpose": "investment",
        "timeline_months": 3,
        "consent_marketing": True,
        "consent_whatsapp": True,
    }
    payload.update(overrides)
    return payload


def submission(**overrides: Any) -> LeadSubmission:
    return LeadSubmission.model_validate(lead_payload(**overrides))


def normalized_lead(**overrides: Any) -> NormalizedLead:
    data: dict[str, Any] = {
        "lead_id": "lead-test-0001",
        "tenant_id": TENANT,
        "full_name": "Demo Lead One",
        "email": "demo.lead.one@example.com",
        "phone_e164": "+971500000001",
        "source": "website",
        "budget_max_aed": "1500000",
        "preferred_locations": ["Business Bay"],
        "property_types": ["apartment"],
        "bedrooms": 1,
        "purpose": "investment",
        "timeline_months": 3,
        "consent_marketing": True,
        "consent_whatsapp": True,
    }
    data.update(overrides)
    return NormalizedLead.model_validate(data)


def integration_enabled() -> bool:
    return os.environ.get("RUN_INTEGRATION_TESTS") == "1"
