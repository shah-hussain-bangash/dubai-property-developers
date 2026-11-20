"""Generic tenant-scoped async repository."""

from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class TenantRepository(Generic[ModelT]):  # noqa: UP046 -- Retain the public Generic/TypeVar API and runtime introspection.
    """All queries are filtered by ``organization_id`` to enforce tenant isolation."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        stmt = select(self.model).where(
            self.model.id == entity_id,  # type: ignore[attr-defined]
            self.model.organization_id == self.organization_id,  # type: ignore[attr-defined]
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add(self, **values: Any) -> ModelT:
        entity = self.model(organization_id=self.organization_id, **values)
        self.session.add(entity)
        await self.session.flush()
        return entity
