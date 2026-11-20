from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.leads.models import NormalizedLead


class MarketingInput(BaseModel):
    leads: list[NormalizedLead] = Field(max_length=10_000)
    campaign_goal: str = Field(default="re-engagement", max_length=200)


class CampaignDraft(BaseModel):
    segment: str
    audience_size: int
    headline: str
    body: str
    status: str = "draft_requires_approval"


class MarketingOutput(BaseModel):
    segments: dict[str, list[str]]
    drafts: list[CampaignDraft]
    excluded_without_consent: int
    recommendations: list[str]
