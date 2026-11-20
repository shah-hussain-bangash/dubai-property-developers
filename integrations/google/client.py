"""Google services (Calendar) adapter - interface and mock only.

A live adapter requires an OAuth 2.0 / service-account setup that is not part of
this foundation. Until then only MOCK mode is available.
"""

from __future__ import annotations

import itertools
from datetime import datetime
from typing import Any, Protocol

from core.exceptions.errors import IntegrationNotConfiguredError
from integrations.base import IntegrationConfig
from schemas.integrations.models import ApiAccessStatus, IntegrationDescriptor


class GoogleConfig(IntegrationConfig):
    credentials_file: str | None = None
    calendar_id: str = "primary"

    @property
    def is_configured(self) -> bool:
        return bool(self.credentials_file)


class CalendarClient(Protocol):
    async def create_event(
        self,
        *,
        summary: str,
        start: datetime,
        end: datetime,
        attendee_emails: list[str],
        description: str,
        idempotency_key: str,
    ) -> str: ...


class MockCalendarClient:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._ids = itertools.count(1)
        self._seen: dict[str, str] = {}

    async def create_event(
        self,
        *,
        summary: str,
        start: datetime,
        end: datetime,
        attendee_emails: list[str],
        description: str,
        idempotency_key: str,
    ) -> str:
        if idempotency_key in self._seen:
            return self._seen[idempotency_key]
        if end <= start:
            raise ValueError("event end must be after start")
        event_id = f"mock-event-{next(self._ids):05d}"
        self.events.append(
            {"id": event_id, "summary": summary, "start": start, "end": end, "attendees": attendee_emails}
        )
        self._seen[idempotency_key] = event_id
        return event_id


class UnimplementedGoogleCalendarClient:
    async def create_event(self, **_: Any) -> str:
        raise IntegrationNotConfiguredError("Google Calendar live adapter is not implemented yet")


def descriptor(config: GoogleConfig) -> IntegrationDescriptor:
    return IntegrationDescriptor(
        name="google",
        display_name="Google Workspace (Calendar)",
        mode=config.mode,
        configured=config.is_configured,
        api_access=ApiAccessStatus.DOCUMENTED_API,
        notes="Mock only. Live adapter pending OAuth/service-account setup.",
    )
