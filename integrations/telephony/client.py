"""Telephony adapter - provider not yet selected. Interface + mock only."""

from __future__ import annotations

import itertools
from typing import Any, Protocol

from core.exceptions.errors import IntegrationNotConfiguredError
from integrations.base import IntegrationConfig
from schemas.integrations.models import ApiAccessStatus, IntegrationDescriptor


class TelephonyConfig(IntegrationConfig):
    provider: str | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.provider)


class TelephonyClient(Protocol):
    async def request_callback(self, *, to_e164: str, reason: str, idempotency_key: str) -> str: ...

    async def get_transcript(self, call_id: str) -> str | None: ...


class MockTelephonyClient:
    def __init__(self, transcripts: dict[str, str] | None = None) -> None:
        self.callbacks: list[dict[str, Any]] = []
        self._transcripts = transcripts or {}
        self._ids = itertools.count(1)

    async def request_callback(self, *, to_e164: str, reason: str, idempotency_key: str) -> str:
        call_id = f"mock-call-{next(self._ids):05d}"
        self.callbacks.append(
            {"id": call_id, "to": to_e164, "reason": reason, "key": idempotency_key}
        )
        return call_id

    async def get_transcript(self, call_id: str) -> str | None:
        return self._transcripts.get(call_id)


class UnselectedTelephonyClient:
    async def request_callback(self, **_: Any) -> str:
        raise IntegrationNotConfiguredError("telephony provider not selected")

    async def get_transcript(self, call_id: str) -> str | None:
        raise IntegrationNotConfiguredError("telephony provider not selected")


def descriptor(config: TelephonyConfig) -> IntegrationDescriptor:
    return IntegrationDescriptor(
        name="telephony",
        display_name="Telephony / Voice",
        mode=config.mode,
        configured=config.is_configured,
        api_access=ApiAccessStatus.PROVIDER_NOT_SELECTED,
        notes="Select a provider (and confirm UAE TDRA requirements) before implementing.",
    )
