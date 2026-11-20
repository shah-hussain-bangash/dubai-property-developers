from __future__ import annotations

from typing import Any, ClassVar

from core.exceptions.errors import DomainValidationError, PolicyViolationError
from core.policies.actions import ActionCategory
from core.security.rbac import Permission
from tools.base import BaseTool, ToolSpec
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

    def __init__(self, sender: EmailSender) -> None:
        self._sender = sender

    def validate(self, payload: dict[str, Any]) -> None:
        if "@" not in str(payload.get("to", "")):
            raise DomainValidationError("valid recipient email required")
        if not payload.get("subject") or not payload.get("body"):
            raise DomainValidationError("subject and body are required")
        if payload.get("is_marketing") and not payload.get("consent_marketing"):
            raise PolicyViolationError("marketing email requires recorded marketing consent")

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        message_id = await self._sender.send(
            to=payload["to"],
            subject=payload["subject"],
            body=payload["body"],
            idempotency_key=str(payload.get("idempotency_key", "")),
        )
        return {"message_id": message_id}
