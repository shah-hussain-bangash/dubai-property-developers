"""Parse Meta WhatsApp Cloud API webhook payloads into inbound messages.

Structure per Meta docs: ``entry[].changes[].value.messages[]`` with ``from``,
``id``, ``timestamp``, ``type`` and ``text.body``; ``value.contacts[].profile.name``.
Signature verification (X-Hub-Signature-256) must happen before parsing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel


class InboundWhatsAppMessage(BaseModel):
    message_id: str
    from_e164: str
    profile_name: str | None
    text: str | None
    message_type: str
    received_at: datetime


def parse_meta_webhook(payload: dict[str, Any]) -> list[InboundWhatsAppMessage]:
    messages: list[InboundWhatsAppMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {
                c.get("wa_id"): (c.get("profile") or {}).get("name")
                for c in value.get("contacts", [])
            }
            for msg in value.get("messages", []):
                sender = str(msg.get("from", ""))
                messages.append(
                    InboundWhatsAppMessage(
                        message_id=str(msg.get("id", "")),
                        from_e164=f"+{sender.lstrip('+')}",
                        profile_name=names.get(sender),
                        text=(msg.get("text") or {}).get("body"),
                        message_type=str(msg.get("type", "unknown")),
                        received_at=datetime.fromtimestamp(int(msg.get("timestamp", 0)), UTC),
                    )
                )
    return messages
