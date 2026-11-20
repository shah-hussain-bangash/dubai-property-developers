"""Prepare fictional lead fixtures only inside GitHub's disposable CI database."""

import asyncio
import os
import uuid

from sqlalchemy import select
from sqlalchemy.engine import make_url

import database.models  # noqa: F401 -- Register all model relationships before ORM use.
from core.config.settings import Environment, Settings
from database.models.identity import Organization
from database.repositories.postgres_lead_store import PostgresLeadStore
from database.sessions.engine import create_engine, create_session_factory
from schemas.leads.models import NormalizedLead


async def prepare() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    url = make_url(settings.database_url.get_secret_value())
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or settings.environment != Environment.TEST
        or url.host not in {"localhost", "127.0.0.1"}
        or url.database != "dubai_ai"
        or url.username != "dubai_ai"
    ):
        raise RuntimeError("This preparation is restricted to the local GitHub CI test database")
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            existing = await session.scalar(
                select(Organization).where(Organization.slug == "tenant-isolation-test")
            )
            if existing is None:
                session.add(
                    Organization(
                        id=uuid.uuid4(),
                        name="CI Tenant Isolation (Fictional)",
                        slug="tenant-isolation-test",
                        is_active=True,
                    )
                )
        store = PostgresLeadStore(factory)
        if not await store.list("demo-org"):
            await store.save(
                NormalizedLead(
                    lead_id=str(uuid.uuid4()),
                    tenant_id="demo-org",
                    full_name="CI Template Lead (Fictional)",
                    email="qa@example.com",
                    source="website",
                    dedupe_keys=["ci:template-lead"],
                    consent_marketing=False,
                    consent_whatsapp=False,
                )
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(prepare())
