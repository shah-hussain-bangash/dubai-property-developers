
"""Insert fictional demo data into a *development* database.

Usage: python -m database.seeds.load_demo
Run after: alembic upgrade head

Refuses to run outside development/test.
Idempotent: skips if the demo organization already exists.
Never deletes data.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import database.models  # noqa: F401
from core.config.settings import get_settings
from core.security.rbac import Role as RoleName
from database.models.agent import AIAgent
from database.models.identity import Organization, Role
from database.models.property import (
    PaymentPlan,
    Project,
    Property,
    PropertyUnit,
)
from database.seeds.demo_catalog import DEMO_LISTINGS
from database.sessions.engine import create_engine, create_session_factory

DEMO_ORG_SLUG = "demo-org"


async def load() -> None:
    settings = get_settings()

    if not settings.is_dev_like:
        raise SystemExit(
            "Refusing to seed demo data outside development/test."
        )

    engine = create_engine(settings)

    try:
        await _seed(create_session_factory(engine))
    finally:
        await engine.dispose()


async def _seed(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session, session.begin():

        existing = await session.scalar(
            select(Organization).where(
                Organization.slug == DEMO_ORG_SLUG
            )
        )

        if existing is not None:
            print("Demo organization already present; nothing to do.")
            return

        # STAGE 1: Create demo organization.
        org = Organization(
            id=uuid.uuid4(),
            name="Demo Brokerage (Fictional)",
            slug=DEMO_ORG_SLUG,
        )

        session.add(org)
        await session.flush()

        # STAGE 2: Create roles.
        for role in RoleName:
            existing_role = await session.scalar(
                select(Role).where(Role.name == role.value)
            )

            if existing_role is None:
                session.add(
                    Role(
                        name=role.value,
                        description=f"{role.value} role",
                    )
                )

        await session.flush()

        # STAGE 3: Register AI agents.
        from agents.registry import agent_descriptors

        for descriptor in agent_descriptors():
            session.add(
                AIAgent(
                    agent_key=descriptor.agent_id,
                    name=descriptor.name,
                    version=descriptor.version,
                    implementation_status=(
                        descriptor.implementation_status.value
                    ),
                )
            )

        await session.flush()

        # STAGE 4: Prepare fictional property catalog.
        projects: dict[tuple[str, str], Project] = {}
        properties: dict[tuple[str, str], Property] = {}
        plans: dict[tuple[str, str], PaymentPlan] = {}
        unit_counter: dict[str, int] = defaultdict(int)

        # Create all parent projects first.
        for listing in DEMO_LISTINGS:
            pkey = (listing.developer, listing.project_name)

            if pkey not in projects:
                projects[pkey] = Project(
                    id=uuid.uuid4(),
                    organization_id=org.id,
                    name=listing.project_name,
                    developer_name=listing.developer,
                    community=listing.community,
                    completion_status=(
                        listing.completion_status.value
                    ),
                    handover_quarter=listing.handover_quarter,
                    is_demo=True,
                    data_source=listing.source,
                    data_as_of=listing.data_as_of,
                )

                session.add(projects[pkey])

        await session.flush()

        # STAGE 5: Create properties referencing saved projects.
        for listing in DEMO_LISTINGS:
            pkey = (listing.developer, listing.project_name)
            project = projects[pkey]

            prop_key = (
                listing.project_name,
                listing.property_type.value,
            )

            if prop_key not in properties:
                properties[prop_key] = Property(
                    id=uuid.uuid4(),
                    organization_id=org.id,
                    project_id=project.id,
                    name=(
                        f"{listing.project_name} - "
                        f"{listing.property_type.value}"
                    ),
                    property_type=listing.property_type.value,
                )

                session.add(properties[prop_key])

        await session.flush()

        # STAGE 6: Create payment plans referencing saved projects.
        for listing in DEMO_LISTINGS:
            if listing.payment_plan is None:
                continue

            pkey = (listing.developer, listing.project_name)
            project = projects[pkey]

            plan_key = (
                listing.project_name,
                listing.payment_plan.name,
            )

            if plan_key not in plans:
                pp = listing.payment_plan

                plans[plan_key] = PaymentPlan(
                    id=uuid.uuid4(),
                    organization_id=org.id,
                    project_id=project.id,
                    name=pp.name,
                    down_payment_pct=pp.down_payment_pct,
                    during_construction_pct=(
                        pp.during_construction_pct
                    ),
                    on_handover_pct=pp.on_handover_pct,
                    post_handover_pct=pp.post_handover_pct,
                    post_handover_months=(
                        pp.post_handover_months
                    ),
                )

                session.add(plans[plan_key])

        await session.flush()

        # STAGE 7: Create property units.
        for listing in DEMO_LISTINGS:
            prop_key = (
                listing.project_name,
                listing.property_type.value,
            )

            plan_id = None

            if listing.payment_plan is not None:
                plan_key = (
                    listing.project_name,
                    listing.payment_plan.name,
                )

                plan_id = plans[plan_key].id

            unit_counter[listing.project_name] += 1

            session.add(
                PropertyUnit(
                    organization_id=org.id,
                    property_id=properties[prop_key].id,
                    payment_plan_id=plan_id,
                    unit_ref=listing.listing_id,
                    bedrooms=listing.bedrooms,
                    size_sqft=listing.size_sqft,
                    price_aed=listing.price_aed,
                    availability=listing.availability.value,
                    data_as_of=listing.data_as_of,
                )
            )

        await session.flush()

    print(
        f"Seeded demo organization '{DEMO_ORG_SLUG}' "
        f"with {len(DEMO_LISTINGS)} fictional units!"
    )


if __name__ == "__main__":
    asyncio.run(load())
