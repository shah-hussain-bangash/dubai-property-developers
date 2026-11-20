"""Request/execution correlation context propagated via contextvars."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_tenant_id: ContextVar[str | None] = ContextVar("tenant_id", default=None)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_correlation_id(value: str | None) -> None:
    _correlation_id.set(value)


def get_tenant_id() -> str | None:
    return _tenant_id.get()


def set_tenant_id(value: str | None) -> None:
    _tenant_id.set(value)
