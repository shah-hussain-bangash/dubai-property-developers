from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ImplementationStatus(StrEnum):
    FUNCTIONAL = "functional"  # deterministic logic works end-to-end with mocks
    PARTIAL = "partial"  # contract + some logic; key capabilities pending
    INTERFACE_ONLY = "interface_only"  # contract only; raises/no-ops until implemented


class AgentRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    PENDING_APPROVAL = "pending_approval"
    ESCALATED = "escalated"


class AgentDescriptor(BaseModel):
    agent_id: str
    name: str
    description: str
    responsibilities: list[str]
    implementation_status: ImplementationStatus
    allowed_tools: list[str]
    timeout_seconds: float
    version: str


class AgentListResponse(BaseModel):
    items: list[AgentDescriptor]
    total: int
