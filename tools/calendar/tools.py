from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from core.exceptions.errors import AuthorizationError, DomainValidationError
from core.policies.actions import ActionCategory
from core.resilience.idempotency import make_idempotency_key
from core.security.rbac import Permission
from integrations.google.client import CalendarClient
from tools.base import BaseTool, ToolCallContext, ToolSpec


class CalendarCreateEventTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="calendar.create_event",
        description="Book a meeting or viewing on the team calendar",
        category=ActionCategory.CALENDAR_WRITE,
        permission=Permission.CALENDAR_WRITE,
    )

    def __init__(self, client: CalendarClient, *, tenant_id: str | None = None) -> None:
        self._client = client
        self._tenant_id = tenant_id

    def authorize_context(self, ctx: ToolCallContext) -> None:
        if (
            not self._tenant_id
            or ctx.tenant_id != self._tenant_id
            or ctx.principal.tenant_id != self._tenant_id
        ):
            raise AuthorizationError("Calendar account is not configured for this organization")

    def validate(self, payload: dict[str, Any]) -> None:
        try:
            start = datetime.fromisoformat(payload["start"])
            end = datetime.fromisoformat(payload["end"])
        except (KeyError, ValueError, TypeError) as exc:
            raise DomainValidationError("start and end must be ISO-8601 datetimes") from exc
        if start.tzinfo is None or end.tzinfo is None:
            raise DomainValidationError("start and end must include an explicit UTC offset")
        if end <= start:
            raise DomainValidationError("end must be after start")

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._tenant_id is not None:
            raise AuthorizationError("Organization-bound bookings require a trusted identity")
        return await self._send(payload)

    async def execute_with_context(
        self, payload: dict[str, Any], ctx: ToolCallContext
    ) -> dict[str, Any]:
        self.authorize_context(ctx)
        return await self._send(payload, scope=ctx.tenant_id, agent_id=ctx.agent_id)

    async def _send(
        self, payload: dict[str, Any], *, scope: str | None = None, agent_id: str | None = None
    ) -> dict[str, Any]:
        self.validate(payload)
        key = (
            make_idempotency_key(self.spec.name, payload, scope=scope, agent_id=agent_id)
            if scope is not None
            else str(payload.get("idempotency_key", payload["summary"] + payload["start"]))
        )
        event_id = await self._client.create_event(
            summary=payload["summary"],
            start=datetime.fromisoformat(payload["start"]),
            end=datetime.fromisoformat(payload["end"]),
            attendee_emails=list(payload.get("attendees", [])),
            description=payload.get("description", ""),
            idempotency_key=key,
        )
        return {"event_id": event_id}
