from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from core.exceptions.errors import DomainValidationError, PolicyViolationError
from core.policies.actions import ActionCategory
from core.security.rbac import Permission
from integrations.meta.client import WhatsAppClient
from tools.base import BaseTool, ToolSpec
from tools.whatsapp.policy import is_within_service_window


class WhatsAppSendTool(BaseTool):
    """Payload: to_e164, consent_whatsapp, last_inbound_at (ISO or None), and either
    ``text`` (inside the 24h window) or ``template_name`` + ``language_code``."""

    spec: ClassVar[ToolSpec] = ToolSpec(
        name="whatsapp.send_message",
        description="Send a WhatsApp message to a customer",
        category=ActionCategory.OUTBOUND_MESSAGE,
        permission=Permission.MESSAGES_SEND,
    )

    def __init__(self, client: WhatsAppClient) -> None:
        self._client = client

    def validate(self, payload: dict[str, Any]) -> None:
        if not str(payload.get("to_e164", "")).startswith("+"):
            raise DomainValidationError("to_e164 must be an E.164 number")
        if not payload.get("consent_whatsapp"):
            raise PolicyViolationError("contact has not opted in to WhatsApp messages")
        raw = payload.get("last_inbound_at")
        last_inbound = datetime.fromisoformat(raw) if isinstance(raw, str) else None
        if payload.get("text") and not is_within_service_window(last_inbound):
            raise PolicyViolationError(
                "outside the 24h customer-service window: an approved template is required"
            )
        if not payload.get("text") and not payload.get("template_name"):
            raise DomainValidationError("either text or template_name is required")

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        key = str(payload.get("idempotency_key") or payload["to_e164"] + str(payload.get("text")))
        if payload.get("text"):
            message_id = await self._client.send_text(
                to_e164=payload["to_e164"], body=payload["text"], idempotency_key=key
            )
        else:
            message_id = await self._client.send_template(
                to_e164=payload["to_e164"],
                template_name=payload["template_name"],
                language_code=payload.get("language_code", "en"),
                components=payload.get("components", []),
                idempotency_key=key,
            )
        return {"message_id": message_id}
