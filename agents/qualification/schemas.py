from __future__ import annotations

from pydantic import BaseModel

from schemas.leads.models import LeadRouting, LeadScore, LeadStatus, NormalizedLead


class QualificationInput(BaseModel):
    lead: NormalizedLead


class QualificationResult(BaseModel):
    lead_id: str
    score: LeadScore
    routing: LeadRouting
    status: LeadStatus
