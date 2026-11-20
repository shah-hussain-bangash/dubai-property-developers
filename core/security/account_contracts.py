"""Typed account boundaries shared by trusted service composition."""

from collections.abc import Callable
from typing import Any, Literal, Protocol, TypedDict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.security.rbac import Principal

SessionFactory = Callable[[], AsyncSession]
# The framework resolves heterogeneous sync/async dependency callables. Each
# route parameter retains its concrete actor or service type.
Dependency = Callable[..., Any]


class AccountRecord(TypedDict):
    account_id: UUID
    organization_id: UUID
    full_name: str
    approval_status: Literal["pending", "approved", "rejected"] | None


class VerifiedActor(Protocol):
    @property
    def user_id(self) -> UUID: ...

    @property
    def organization_id(self) -> UUID: ...


class PrincipalFactory(Protocol):
    def __call__(self, *, subject: str, tenant_id: str, roles: frozenset[str]) -> Principal: ...


class ActorFactory(Protocol):
    def __call__(self, *, user_id: UUID, organization_id: UUID) -> VerifiedActor: ...
