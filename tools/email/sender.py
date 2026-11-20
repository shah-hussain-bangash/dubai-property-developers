"""Email delivery contract. No SMTP/ESP provider is configured yet; mock only."""

from __future__ import annotations

import itertools
from typing import Any, Protocol


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, body: str, idempotency_key: str) -> str: ...


class MockEmailSender:
    def __init__(self) -> None:
        self.outbox: list[dict[str, Any]] = []
        self._ids = itertools.count(1)

    async def send(self, *, to: str, subject: str, body: str, idempotency_key: str) -> str:
        message_id = f"mock-email-{next(self._ids):05d}"
        self.outbox.append({"id": message_id, "to": to, "subject": subject, "body": body})
        return message_id
