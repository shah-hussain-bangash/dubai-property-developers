from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SyncOperation(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class WebhookEnvelope(BaseModel):
    source: str
    event_type: str
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    delivery_id: str | None = None
    payload: dict[str, Any]


class ExternalRecordEvent(BaseModel):
    """A change reported by an external system (e.g. EspoCRM) for synchronization."""

    source_system: str
    entity_type: str  # "lead", "contact", "opportunity"
    external_id: str
    operation: SyncOperation
    occurred_at: datetime
    version: str | None = None  # source modifiedAt / etag used for conflict detection
    data: dict[str, Any] = Field(default_factory=dict)
