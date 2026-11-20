import asyncio
import json
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy import delete, select

from core.config.settings import Settings
from database.models.crm import Lead
from database.models.identity import Organization
from database.repositories.postgres_lead_store import lead_dedupe_keys
from database.sessions.engine import create_engine, create_session_factory

API_URL = "http://127.0.0.1:8000/api/v1/leads/demo-process"


async def main():
    settings = Settings()

    if not settings.is_dev_like or settings.integrations_mode != "mock":
        raise RuntimeError("Development mode with mock integrations required")

    token = uuid.uuid4().hex
    email = f"live-api-{token}@example.com"
    phone = "050" + str(int(token[:10], 16) % 10000000).zfill(7)

    payload = {
        "full_name": "Fictional API Test Lead",
        "email": email,
        "phone": phone,
        "source": "website",
        "message": "Fictional test enquiry for a Dubai apartment",
        "budget_min_aed": "900000",
        "budget_max_aed": "1500000",
        "preferred_locations": ["business bay"],
        "property_types": ["apartment"],
        "bedrooms": 1,
        "purpose": "investment",
        "timeline_months": 3,
        "consent_marketing": False,
        "consent_whatsapp": False,
    }

    engine = create_engine(settings)
    factory = create_session_factory(engine)

    def post_lead():
        request = Request(
            API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 -- Fixed loopback HTTP endpoint; redirects are disabled or this is a local acceptance script.
                return json.load(response)
        except HTTPError as exc:
            print("HTTP error:", exc.code)
            print(exc.read().decode("utf-8")[:1500])
            raise

    try:
        print("Starting live API acceptance test")
        print("---------------------------------")

        first = await asyncio.to_thread(post_lead)

        assert first["status"] == "succeeded", first.get("error")
        lead = first["result"]["lead"]
        assert lead is not None
        assert first["result"].get("crm") is not None

        print("1. Live API workflow: PASSED")
        print("2. Mock CRM processing: PASSED")

        lead_id = uuid.UUID(lead["lead_id"])

        async with factory() as session:
            org_id = await session.scalar(
                select(Organization.id).where(Organization.slug == settings.default_tenant_id)
            )

            assert org_id is not None

            stored = await session.scalar(
                select(Lead).where(
                    Lead.organization_id == org_id,
                    Lead.id == lead_id,
                    Lead.email == email,
                )
            )

            assert stored is not None

        print("3. Lead persisted in PostgreSQL: PASSED")

        second = await asyncio.to_thread(post_lead)

        assert second["status"] == "succeeded", second.get("error")
        assert second["result"]["is_duplicate"] is True
        assert second["result"].get("crm") is None
        assert second["steps"][-1]["name"] == "duplicate_gate"

        print("4. Duplicate lead detected: PASSED")
        print("5. Duplicate CRM processing prevented: PASSED")

        print()
        print("LIVE API POSTGRESQL ACCEPTANCE TEST: PASSED")

    finally:
        try:
            async with factory() as session, session.begin():
                org_id = await session.scalar(
                    select(Organization.id).where(Organization.slug == settings.default_tenant_id)
                )

                if org_id is not None:
                    ids = list(
                        (
                            await session.scalars(
                                select(Lead.id).where(
                                    Lead.organization_id == org_id,
                                    Lead.email == email,
                                )
                            )
                        ).all()
                    )

                    if ids:
                        await session.execute(
                            delete(lead_dedupe_keys).where(
                                lead_dedupe_keys.c.organization_id == org_id,
                                lead_dedupe_keys.c.lead_id.in_(ids),
                            )
                        )

                        await session.execute(
                            delete(Lead).where(
                                Lead.organization_id == org_id,
                                Lead.id.in_(ids),
                                Lead.email == email,
                            )
                        )

            print("Fictional test record cleanup: COMPLETED")

        finally:
            await engine.dispose()
            print("Database connection: CLOSED")


if __name__ == "__main__":
    asyncio.run(main())
