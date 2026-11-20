from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from core.exceptions.errors import DomainValidationError
from core.policies.actions import ActionCategory
from core.security.rbac import Permission
from integrations.google.client import CalendarClient
from tools.base import BaseTool, ToolSpec


class CalendarCreateEventTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="calendar.create_event",
        description="Book a meeting or viewing on the team calendar",
        category=ActionCategory.CALENDAR_WRITE,
        permission=Permission.CALENDAR_WRITE,
    )

    def __init__(self, client: CalendarClient) -> None:
        self._client = client

    def validate(self, payload: dict[str, Any]) -> None:
        try:
            start = datetime.fromisoformat(payload["start"])
            end = datetime.fromisoformat(payload["end"])
        except (KeyError, ValueError) as exc:
            raise DomainValidationError("start and end must be ISO-8601 datetimes") from exc
        if end <= start:
            raise DomainValidationError("end must be after start")

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        event_id = await self._client.create_event(
            summary=payload["summary"],
            start=datetime.fromisoformat(payload["start"]),
            end=datetime.fromisoformat(payload["end"]),
            attendee_emails=list(payload.get("attendees", [])),
            description=payload.get("description", ""),
            idempotency_key=str(payload.get("idempotency_key", payload["summary"] + payload["start"])),
        )
        return {"event_id": event_id}
