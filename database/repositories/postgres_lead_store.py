
"""PostgreSQL-backed lead storage for AI workflows.

Implements the LeadStore protocol:
- save()
- list()
- find_by_dedupe_keys()

Requires Alembic migrations:
- 0002_lead_persistence
- 0003_unique_lead_dedupe_keys
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import (
    Column,
    MetaData,
    String,
    Table,
    Uuid,
    delete,
    insert,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from database.models.crm import Lead
from database.models.identity import Organization
from schemas.leads.models import NormalizedLead


# Existing table created by Migration 0002.
# Migration 0003 enforces organization-wide key uniqueness.
# This mapping does not create another database table.
lead_dedupe_keys = Table(
    "lead_dedupe_keys",
    MetaData(),
    Column("id", Uuid, primary_key=True),
    Column("organization_id", Uuid, nullable=False),
    Column("lead_id", Uuid, nullable=False),
    Column("dedupe_key", String(128), nullable=False),
)


class PostgresLeadStore:
    """Persistent tenant-scoped implementation of LeadStore."""

    DUPLICATE_CONSTRAINT = "uq_lead_dedupe_keys_org_key"

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory

    async def _organization_id(
        self,
        session: AsyncSession,
        tenant_id: str,
    ) -> uuid.UUID:
        """Resolve an active organization from a tenant slug."""

        if not tenant_id:
            raise ValueError("tenant_id is required")

        organization_id = await session.scalar(
            select(Organization.id).where(
                Organization.slug == tenant_id,
                Organization.is_active.is_(True),
            )
        )

        if organization_id is None:
            raise ValueError(
                f"Unknown or inactive organization: {tenant_id}"
            )

        return organization_id

    @staticmethod
    def _validated_keys(keys: list[str]) -> list[str]:
        """Validate and remove repeated deduplication keys."""

        cleaned: list[str] = []
        seen: set[str] = set()

        for key in keys:
            if not isinstance(key, str):
                raise ValueError(
                    "Deduplication keys must be strings"
                )

            if not key or not key.strip():
                raise ValueError(
                    "Deduplication keys cannot be empty"
                )

            if len(key) > 128:
                raise ValueError(
                    "Deduplication key exceeds 128 characters"
                )

            if key not in seen:
                seen.add(key)
                cleaned.append(key)

        return cleaned

    @staticmethod
    def _to_normalized(
        row: Lead,
        tenant_id: str,
        keys: list[str],
    ) -> NormalizedLead:
        """Convert a database Lead into a NormalizedLead."""

        return NormalizedLead(
            lead_id=str(row.id),
            tenant_id=tenant_id,
            full_name=row.full_name,
            email=row.email,
            phone_e164=row.phone_e164,
            phone_region=row.phone_region,
            source=row.source,
            message=row.message,
            budget_min_aed=row.budget_min_aed,
            budget_max_aed=row.budget_max_aed,
            preferred_locations=row.preferred_locations or [],
            property_types=row.property_types or [],
            bedrooms=row.bedrooms,
            purpose=row.purpose,
            timeline_months=row.timeline_months,
            consent_marketing=bool(row.consent_marketing),
            consent_whatsapp=bool(row.consent_whatsapp),
            external_ref=row.external_ref,
            dedupe_keys=keys,
            received_at=row.received_at,
            status=row.status,
        )

    async def _get_keys_for_leads(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        lead_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[str]]:
        """Retrieve duplicate keys for multiple leads."""

        if not lead_ids:
            return {}

        statement = (
            select(
                lead_dedupe_keys.c.lead_id,
                lead_dedupe_keys.c.dedupe_key,
            )
            .where(
                lead_dedupe_keys.c.organization_id
                == organization_id,
                lead_dedupe_keys.c.lead_id.in_(lead_ids),
            )
            .order_by(
                lead_dedupe_keys.c.lead_id,
                lead_dedupe_keys.c.dedupe_key,
            )
        )

        result = await session.execute(statement)

        keys_by_lead: dict[
            uuid.UUID, list[str]
        ] = defaultdict(list)

        for lead_id, key in result.all():
            keys_by_lead[lead_id].append(key)

        return dict(keys_by_lead)

    @classmethod
    def _is_duplicate_constraint_error(
        cls,
        exc: IntegrityError,
    ) -> bool:
        """Identify the PostgreSQL duplicate-key constraint.

        SQLAlchemy database drivers expose the underlying
        PostgreSQL error through slightly different objects.
        """

        current: BaseException | None = exc.orig
        visited: set[int] = set()

        while current is not None:
            if id(current) in visited:
                break

            visited.add(id(current))

            diag = getattr(current, "diag", None)

            constraint_name = (
                getattr(diag, "constraint_name", None)
                or getattr(current, "constraint_name", None)
            )

            if constraint_name == cls.DUPLICATE_CONSTRAINT:
                return True

            current = (
                getattr(current, "__cause__", None)
                or getattr(current, "__context__", None)
            )

        # Some drivers include the constraint name only in
        # their original exception text.
        return cls.DUPLICATE_CONSTRAINT in str(exc.orig)

    async def save(self, lead: NormalizedLead) -> None:
        """Insert/update a lead and synchronize duplicate keys.

        A successful transaction commits all changes.
        Any exception rolls back the entire transaction.
        """

        try:
            lead_id = uuid.UUID(lead.lead_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError(
                "lead_id must be a valid UUID"
            ) from exc

        keys = self._validated_keys(lead.dedupe_keys)

        try:
            async with self.session_factory() as session:
                async with session.begin():

                    organization_id = (
                        await self._organization_id(
                            session,
                            lead.tenant_id,
                        )
                    )

                    # Lock an existing lead before updating.
                    # Check global ID ownership to prevent
                    # cross-organization modifications.
                    existing = await session.scalar(
                        select(Lead)
                        .where(Lead.id == lead_id)
                        .with_for_update()
                    )

                    if (
                        existing is not None
                        and existing.organization_id
                        != organization_id
                    ):
                        raise ValueError(
                            "Lead belongs to another organization"
                        )

                    # Friendly pre-check for sequential duplicates.
                    # Migration 0003 handles concurrent collisions.
                    if keys:
                        duplicate_query = (
                            select(
                                lead_dedupe_keys.c.lead_id
                            )
                            .where(
                                lead_dedupe_keys.c.organization_id
                                == organization_id,
                                lead_dedupe_keys.c.dedupe_key.in_(
                                    keys
                                ),
                                lead_dedupe_keys.c.lead_id
                                != lead_id,
                            )
                            .limit(1)
                        )

                        duplicate_owner = (
                            await session.scalar(
                                duplicate_query
                            )
                        )

                        if duplicate_owner is not None:
                            raise ValueError(
                                "One or more deduplication keys "
                                "already belong to another lead"
                            )

                    values: dict[str, Any] = {
                        "full_name": lead.full_name,
                        "email": lead.email,
                        "phone_e164": lead.phone_e164,
                        "phone_region": lead.phone_region,
                        "source": lead.source.value,
                        "status": lead.status.value,
                        "purpose": lead.purpose.value,
                        "message": lead.message,
                        "budget_min_aed": lead.budget_min_aed,
                        "budget_max_aed": lead.budget_max_aed,
                        "preferred_locations": list(
                            lead.preferred_locations
                        ),
                        "property_types": [
                            item.value
                            for item in lead.property_types
                        ],
                        "bedrooms": lead.bedrooms,
                        "timeline_months": lead.timeline_months,
                        "consent_marketing": (
                            lead.consent_marketing
                        ),
                        "consent_whatsapp": (
                            lead.consent_whatsapp
                        ),
                        "external_ref": lead.external_ref,
                        "received_at": lead.received_at,
                        "dedupe_key": (
                            keys[0] if keys else None
                        ),
                    }

                    if existing is None:
                        session.add(
                            Lead(
                                id=lead_id,
                                organization_id=organization_id,
                                **values,
                            )
                        )
                    else:
                        for field_name, value in values.items():
                            setattr(
                                existing,
                                field_name,
                                value,
                            )

                    # Save the parent lead before its keys.
                    await session.flush()

                    # Remove old keys belonging only to this lead.
                    await session.execute(
                        delete(lead_dedupe_keys).where(
                            lead_dedupe_keys.c.organization_id
                            == organization_id,
                            lead_dedupe_keys.c.lead_id
                            == lead_id,
                        )
                    )

                    # Store every normalized duplicate key.
                    if keys:
                        await session.execute(
                            insert(lead_dedupe_keys),
                            [
                                {
                                    "id": uuid.uuid4(),
                                    "organization_id": (
                                        organization_id
                                    ),
                                    "lead_id": lead_id,
                                    "dedupe_key": key,
                                }
                                for key in keys
                            ],
                        )

                # Commit occurs after session.begin() succeeds.

        except IntegrityError as exc:
            # Reaching this handler means the database
            # transaction has already exited and rolled back.
            if self._is_duplicate_constraint_error(exc):
                raise ValueError(
                    "One or more deduplication keys already "
                    "belong to another lead"
                ) from exc

            # Do not disguise unrelated database failures.
            raise

    async def list(
        self,
        tenant_id: str,
    ) -> list[NormalizedLead]:
        """Return leads belonging to one organization."""

        async with self.session_factory() as session:
            organization_id = await self._organization_id(
                session,
                tenant_id,
            )

            result = await session.scalars(
                select(Lead)
                .where(
                    Lead.organization_id
                    == organization_id
                )
                .order_by(
                    Lead.received_at.desc(),
                    Lead.id,
                )
            )

            rows = result.all()

            keys_by_lead = await self._get_keys_for_leads(
                session,
                organization_id,
                [row.id for row in rows],
            )

            return [
                self._to_normalized(
                    row,
                    tenant_id,
                    keys_by_lead.get(row.id, []),
                )
                for row in rows
            ]

    async def find_by_dedupe_keys(
        self,
        tenant_id: str,
        keys: list[str],
    ) -> list[NormalizedLead]:
        """Find leads sharing at least one duplicate key."""

        if not keys:
            return []

        wanted = self._validated_keys(keys)

        if not wanted:
            return []

        async with self.session_factory() as session:
            organization_id = await self._organization_id(
                session,
                tenant_id,
            )

            statement = (
                select(Lead)
                .join(
                    lead_dedupe_keys,
                    (
                        lead_dedupe_keys.c.lead_id
                        == Lead.id
                    )
                    & (
                        lead_dedupe_keys.c.organization_id
                        == Lead.organization_id
                    ),
                )
                .where(
                    Lead.organization_id
                    == organization_id,
                    lead_dedupe_keys.c.dedupe_key.in_(
                        wanted
                    ),
                )
                .distinct()
            )

            result = await session.scalars(statement)
            rows = result.all()

            keys_by_lead = await self._get_keys_for_leads(
                session,
                organization_id,
                [row.id for row in rows],
            )

            return [
                self._to_normalized(
                    row,
                    tenant_id,
                    keys_by_lead.get(row.id, []),
                )
                for row in rows
            ]
