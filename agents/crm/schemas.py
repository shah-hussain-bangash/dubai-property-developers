from __future__ import annotations

from pydantic import BaseModel

from schemas.leads.models import LeadRouting, LeadScore, NormalizedLead


class CRMUpsertInput(BaseModel):
    lead: NormalizedLead
    score: LeadScore | None = None
    routing: LeadRouting | None = None


class CRMUpsertResult(BaseModel):
    lead_id: str
    external_id: str | None
    created: bool
    status: str  # "executed" | "pending_approval" | "replayed"
    approval_id: str | None = None
    note_id: str | None = None
