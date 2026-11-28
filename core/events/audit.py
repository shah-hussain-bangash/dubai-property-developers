"""Audit trail interface. Every sensitive or external action emits an AuditEvent."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from core.observability.context import get_correlation_id
from core.security.redaction import redact_value


class AuditEvent(BaseModel):
    audit_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tenant_id: str
    actor: str
    action: str
    resource_type: str
    resource_id: str | None = None
    outcome: str  # e.g. "executed", "denied", "pending_approval", "failed"
    correlation_id: str | None = Field(default_factory=get_correlation_id)
    details: dict[str, Any] = Field(default_factory=dict)

    def redacted(self) -> AuditEvent:
        return self.model_copy(update={"details": redact_value(self.details)})


class AuditSink(Protocol):
    async def record(self, event: AuditEvent) -> None: ...


class InMemoryAuditSink:
    """Process-local redacted records with detached diagnostic read views."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    @property
    def events(self) -> list[AuditEvent]:
        return [event.model_copy(deep=True) for event in self._events]

    async def record(self, event: AuditEvent) -> None:
        self._events.append(event.redacted().model_copy(deep=True))
