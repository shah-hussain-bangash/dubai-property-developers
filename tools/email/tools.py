from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from core.exceptions.errors import AuthorizationError, DomainValidationError, PolicyViolationError
from core.policies.actions import ActionCategory
from core.resilience.idempotency import make_idempotency_key
from core.security.rbac import Permission
from knowledge.assigned_sources import AssignedSources
from tools.base import BaseTool, ToolCallContext, ToolSpec
from tools.email.sender import EmailSender
from tools.email.templates import render_template


class EmailRenderTemplateTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="email.render_template",
        description="Render an approved email template into a draft",
        category=ActionCategory.READ,
    )

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        subject, body = render_template(payload["template"], payload.get("values", {}))
        return {"subject": subject, "body": body}


class EmailSendTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="email.send",
        description="Send an email to a customer",
        category=ActionCategory.OUTBOUND_MESSAGE,
        permission=Permission.MESSAGES_SEND,
    )

    def __init__(
        self, sender: EmailSender, assigned_sources: AssignedSources | None = None
    ) -> None:
        self._sender = sender
        self._assigned_sources = assigned_sources

    def validate(self, payload: dict[str, Any]) -> None:
        if "@" not in str(payload.get("to", "")):
            raise DomainValidationError("valid recipient email required")
        if not payload.get("subject") or not payload.get("body"):
            raise DomainValidationError("subject and body are required")
        if payload.get("is_marketing") and payload.get("consent_marketing") is not True:
            raise PolicyViolationError("marketing email requires recorded marketing consent")

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._assigned_sources is not None:
            raise AuthorizationError("Assigned-source sends require a trusted caller identity")
        return await self._send(payload)

    async def execute_with_context(
        self, payload: dict[str, Any], ctx: ToolCallContext
    ) -> dict[str, Any]:
        if self._assigned_sources is not None:
            await asyncio.to_thread(
                self._assigned_sources.validate_message,
                ctx.tenant_id,
                ctx.agent_id,
                payload.get("knowledge_citations"),
                payload["body"],
                payload["subject"],
            )
        return await self._send(payload, scope=ctx.tenant_id, agent_id=ctx.agent_id)

    async def _send(
        self, payload: dict[str, Any], *, scope: str | None = None, agent_id: str | None = None
    ) -> dict[str, Any]:
        self.validate(payload)
        key = (
            make_idempotency_key(self.spec.name, payload, scope=scope, agent_id=agent_id)
            if scope is not None
            else str(payload.get("idempotency_key", ""))
        )
        message_id = await self._sender.send(
            to=payload["to"],
            subject=payload["subject"],
            body=payload["body"],
            idempotency_key=key,
        )
        return {"message_id": message_id}
