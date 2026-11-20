"""Mapping between platform leads and EspoCRM Lead fields."""

from __future__ import annotations

from typing import Any

from schemas.leads.models import LeadScore, LeadSource, NormalizedLead

# EspoCRM default Lead.source options; adjust if your instance customizes them.
_SOURCE_MAP = {
    LeadSource.WEBSITE: "Web Site",
    LeadSource.EMAIL: "Email",
    LeadSource.PHONE: "Call",
    LeadSource.REFERRAL: "Partner",
}


def split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split()
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]


def to_espocrm_lead(lead: NormalizedLead, score: LeadScore | None) -> dict[str, Any]:
    first, last = split_name(lead.full_name)
    description_lines = [f"Platform lead id: {lead.lead_id}", f"Source: {lead.source.value}"]
    if score:
        description_lines.append(
            f"AI score: {score.score} ({score.category.value}, {score.model_version})"
        )
    if lead.preferred_locations:
        description_lines.append("Preferred locations: " + ", ".join(lead.preferred_locations))
    data: dict[str, Any] = {
        "firstName": first,
        "lastName": last,
        "source": _SOURCE_MAP.get(lead.source, "Other"),
        "description": "\n".join(description_lines),
    }
    if lead.email:
        data["emailAddress"] = lead.email
    if lead.phone_e164:
        data["phoneNumber"] = lead.phone_e164
    return data
