"""Human-in-the-loop approval requests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from core.exceptions.errors import ConflictError, NotFoundError
from core.security.redaction import redact_value


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalRequest(BaseModel):
    approval_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    tenant_id: str
    tool_name: str
    action_category: str
    requested_by_agent: str | None = None
    requested_by: str
    reason: str
    # The payload needed to execute the action once approved. Treat as sensitive:
    # encrypt at rest when persisted (see docs/security).
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    correlation_id: str | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(UTC) + timedelta(hours=48))
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None

    def display_payload(self) -> dict[str, Any]:
        return redact_value(self.payload)  # type: ignore[no-any-return]


class ApprovalStore(Protocol):
    async def create(self, request: ApprovalRequest) -> ApprovalRequest: ...

    async def get(self, approval_id: str) -> ApprovalRequest: ...

    async def find_by_idempotency_key(self, key: str) -> ApprovalRequest | None: ...

    async def decide(
        self, approval_id: str, *, approved: bool, decided_by: str, note: str | None = None
    ) -> ApprovalRequest: ...

    async def list_pending(self, tenant_id: str) -> list[ApprovalRequest]: ...


class InMemoryApprovalStore:
    def __init__(self) -> None:
        self._items: dict[str, ApprovalRequest] = {}

    async def create(self, request: ApprovalRequest) -> ApprovalRequest:
        if request.approval_id in self._items:
            raise ConflictError(f"approval {request.approval_id} already exists")
        saved = request.model_copy(deep=True)
        self._expire_if_due(saved)
        self._items[saved.approval_id] = saved
        return saved.model_copy(deep=True)

    async def get(self, approval_id: str) -> ApprovalRequest:
        try:
            request = self._items[approval_id]
            self._expire_if_due(request)
            return request.model_copy(deep=True)
        except KeyError as exc:
            raise NotFoundError(f"approval {approval_id} not found") from exc

    async def find_by_idempotency_key(self, key: str) -> ApprovalRequest | None:
        request = next(
            (r for r in reversed(self._items.values()) if r.idempotency_key == key), None
        )
        if request is None:
            return None
        self._expire_if_due(request)
        return request.model_copy(deep=True)

    async def decide(
        self, approval_id: str, *, approved: bool, decided_by: str, note: str | None = None
    ) -> ApprovalRequest:
        request = await self.get(approval_id)
        if request.status != ApprovalStatus.PENDING:
            raise ConflictError(f"approval {approval_id} already {request.status}")
        if request.expires_at <= datetime.now(UTC):
            request.status = ApprovalStatus.EXPIRED
            self._items[approval_id] = request.model_copy(deep=True)
            raise ConflictError(f"approval {approval_id} expired")
        request.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        request.decided_by = decided_by
        request.decided_at = datetime.now(UTC)
        request.decision_note = note
        self._items[approval_id] = request.model_copy(deep=True)
        return request

    async def list_pending(self, tenant_id: str) -> list[ApprovalRequest]:
        now = datetime.now(UTC)
        for request in self._items.values():
            if request.tenant_id == tenant_id:
                self._expire_if_due(request, now=now)
        return [
            r.model_copy(deep=True)
            for r in self._items.values()
            if r.tenant_id == tenant_id and r.status == ApprovalStatus.PENDING
        ]

    @staticmethod
    def _expire_if_due(request: ApprovalRequest, *, now: datetime | None = None) -> None:
        if request.status != ApprovalStatus.PENDING:
            return
        if request.expires_at <= (now or datetime.now(UTC)):
            request.status = ApprovalStatus.EXPIRED
