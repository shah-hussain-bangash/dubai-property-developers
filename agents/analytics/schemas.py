from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from schemas.leads.models import NormalizedLead


class AnalyticsInput(BaseModel):
    leads: list[NormalizedLead] = Field(default_factory=list, max_length=50_000)
    include_agent_performance: bool = True


class AgentPerformance(BaseModel):
    agent_id: str
    runs: int
    success_rate: float
    avg_duration_ms: float


class AnalyticsOutput(BaseModel):
    sales: dict[str, Any]
    agent_performance: list[AgentPerformance] = Field(default_factory=list)
