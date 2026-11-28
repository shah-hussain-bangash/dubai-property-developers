from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from schemas.conversations.models import Channel, Citation


class FollowUpTask(BaseModel):
    task_id: str
    lead_id: str
    contact_first_name: str
    channel: Channel
    due_at: datetime
    status: str = "open"
    attempts: int = Field(default=0, ge=0)
    to_e164: str | None = None
    email: str | None = None
    last_inbound_at: datetime | None = None
    consent_whatsapp: bool = False
    consent_marketing: bool = False
    customer_replied_since: bool = False
    knowledge_query: str | None = Field(default=None, min_length=3, max_length=1000)


class FollowUpInput(BaseModel):
    tasks: list[FollowUpTask] = Field(max_length=500)
    now: datetime | None = None
    dispatch: bool = False  # True = request sends (approval-gated) for prepared actions


class FollowUpAction(BaseModel):
    task_id: str
    lead_id: str
    channel: Channel
    template: str | None
    draft_text: str
    requires_approval: bool = True
    send_status: str | None = None
    approval_id: str | None = None
    error: str | None = None
    citations: list[Citation] = Field(default_factory=list)


class SkippedTask(BaseModel):
    task_id: str
    reason: str


class FollowUpPlan(BaseModel):
    actions: list[FollowUpAction] = Field(default_factory=list)
    escalations: list[SkippedTask] = Field(default_factory=list)
    skipped: list[SkippedTask] = Field(default_factory=list)
