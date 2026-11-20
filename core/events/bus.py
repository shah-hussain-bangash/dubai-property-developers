"""Domain events and a minimal in-process event bus.

The bus interface is deliberately small so it can be backed by Redis Streams or a
message broker later without changing publishers.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from core.observability.context import get_correlation_id
from core.observability.logging import get_logger

logger = get_logger(__name__)


class DomainEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    event_type: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = Field(default_factory=get_correlation_id)
    tenant_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


Handler = Callable[[DomainEvent], Awaitable[None]]


class EventBus(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...

    def subscribe(self, event_type: str, handler: Handler) -> None: ...


class InMemoryEventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self.published: list[DomainEvent] = []

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        self.published.append(event)
        for handler in [*self._handlers.get(event.event_type, []), *self._handlers.get("*", [])]:
            try:
                await handler(event)
            except Exception:  # a failing subscriber must not break the publisher
                logger.exception("event handler failed", extra={"event_type": event.event_type})
