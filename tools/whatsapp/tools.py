from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, ClassVar

from core.exceptions.errors import AuthorizationError, DomainValidationError, PolicyViolationError
from core.memory.base import ScopedMemoryProvider
from core.policies.actions import ActionCategory
from core.security.rbac import Permission
from integrations.meta.client import WhatsAppClient
from knowledge.assigned_sources import AssignedSources
from tools.base import BaseTool, ToolCallContext, ToolSpec
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

    def __init__(
        self,
        client: WhatsAppClient,
        assigned_sources: AssignedSources | None = None,
        memory: ScopedMemoryProvider | None = None,
    ) -> None:
        self._client = client
        self._assigned_sources = assigned_sources
        self._memory = memory

    def validate(self, payload: dict[str, Any]) -> None:
        if not str(payload.get("to_e164", "")).startswith("+"):
            raise DomainValidationError("to_e164 must be an E.164 number")
        if not payload.get("consent_whatsapp"):
            raise PolicyViolationError("contact has not opted in to WhatsApp messages")
        raw = payload.get("last_inbound_at")
        last_inbound = None
        if raw is not None:
            if not isinstance(raw, str):
                raise DomainValidationError("last_inbound_at must be an ISO timestamp or null")
            try:
                last_inbound = datetime.fromisoformat(raw)
            except ValueError:
                raise DomainValidationError(
                    "last_inbound_at must be an ISO timestamp or null"
                ) from None
        if payload.get("text") and not is_within_service_window(last_inbound):
            raise PolicyViolationError(
                "outside the 24h customer-service window: an approved template is required"
            )
        if not payload.get("text") and not payload.get("template_name"):
            raise DomainValidationError("either text or template_name is required")

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._assigned_sources is not None or self._memory is not None:
            raise AuthorizationError("Conversation-bound sends require a trusted caller identity")
        return await self._send(payload)

    async def execute_with_context(
        self, payload: dict[str, Any], ctx: ToolCallContext
    ) -> dict[str, Any]:
        if self._assigned_sources is not None:
            if payload.get("template_name"):
                raise PolicyViolationError(
                    "Provider template content is not assigned-source verified"
                )
            await asyncio.to_thread(
                self._assigned_sources.validate_message,
                ctx.tenant_id,
                ctx.agent_id,
                payload.get("knowledge_citations"),
                payload.get("text", ""),
            )
        if self._memory is not None and ctx.agent_id == "whatsapp":
            conversation = payload.get("conversation_id")
            if not isinstance(conversation, str) or not conversation:
                raise PolicyViolationError("Conversation consent requires a fresh approved reply")
            state = await self._memory.scoped(ctx.tenant_id, "whatsapp").get_state(conversation)
            if (
                state.get("opted_out")
                or not state.get("consent_whatsapp")
                or state.get("from_e164") != payload.get("to_e164")
            ):
                raise PolicyViolationError(
                    "Conversation consent changed; prepare a new approved reply"
                )
        return await self._send(payload)

    async def _send(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Queue/lock/source-check waits must not preserve an expired service window.
        self.validate(payload)
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
