from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from schemas.conversations.models import Channel, CustomerIntent


class RequestType(StrEnum):
    LEAD_SUBMISSION = "lead_submission"
    CUSTOMER_MESSAGE = "customer_message"
    FOLLOWUP_DUE = "followup_due"
    CRM_EVENT = "crm_event"
    KNOWLEDGE_QUESTION = "knowledge_question"
    PROPERTY_SEARCH = "property_search"
    ANALYTICS = "analytics"


class SupervisorRequest(BaseModel):
    request_type: RequestType
    text: str | None = Field(default=None, max_length=4096)
    channel: Channel | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SupervisorPlan(BaseModel):
    workflow_id: str | None
    agent_sequence: list[str]
    intent: CustomerIntent | None = None
    requires_human: bool = False
    reasons: list[str] = Field(default_factory=list)
    injection_signals: list[str] = Field(default_factory=list)
