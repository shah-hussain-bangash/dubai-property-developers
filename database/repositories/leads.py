from __future__ import annotations

from sqlalchemy import or_, select

from database.models.crm import Lead
from database.repositories.base import TenantRepository


class LeadRepository(TenantRepository[Lead]):
    model = Lead

    async def find_by_contact(self, *, email: str | None, phone_e164: str | None) -> list[Lead]:
        conditions = []
        if email:
            conditions.append(Lead.email == email)
        if phone_e164:
            conditions.append(Lead.phone_e164 == phone_e164)
        if not conditions:
            return []
        stmt = (
            select(Lead)
            .where(Lead.organization_id == self.organization_id, or_(*conditions))
            .order_by(Lead.received_at.desc())
            .limit(20)
        )
        return list((await self.session.execute(stmt)).scalars())
