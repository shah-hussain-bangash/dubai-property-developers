from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.leads.models import NormalizedLead


class LeadIntakeResult(BaseModel):
    lead: NormalizedLead
    is_duplicate: bool
    duplicate_of: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
