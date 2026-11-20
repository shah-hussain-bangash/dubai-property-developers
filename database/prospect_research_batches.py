"""Tenant-scoped batch checkpoints with a session lock spanning durable commits."""

import asyncio
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal, cast

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Uuid,
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from core.config.settings import Settings
from core.prospect_research_batch import (
    ROLES,
    BatchQuery,
    ResearchBatch,
    Scope,
    advance_batch,
    transition,
)
from database.prospect_research import RevisionConflict, metadata, organization
from database.research_contracts import BatchCreation, BatchMutation, StateSnapshot

batches = Table(
    "prospect_research_batches_v1",
    metadata,
    Column(
        "organization_id",
        Uuid,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column("batch_id", String(80), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("state", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("revision > 0", name="ck_prospect_batch_revision"),
)


class BatchNotFound(Exception):
    pass


class BatchBusy(Exception):
    pass


class BatchCapacity(Exception):
    pass


SECTORS = (
    "real estate",
    "investment management",
    "construction",
    "technology",
    "hospitality",
    "professional services",
    "trade and logistics",
    "manufacturing",
    "retail",
    "finance",
)


def decode(row: Mapping[Any, Any], slug: str, batch_id: str) -> StateSnapshot:
    state = ResearchBatch.model_validate(row["state"])
    if state.tenant_id != slug or state.id != batch_id:
        raise ValueError("Batch identity mismatch")
    return {"revision": row["revision"], "state": state.model_dump(mode="json")}


def read_batch(conn: Connection, slug: str, batch_id: str) -> StateSnapshot:
    org = organization(conn, slug)
    row = (
        conn.execute(
            select(batches.c.revision, batches.c.state).where(
                batches.c.organization_id == org, batches.c.batch_id == batch_id
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise BatchNotFound()
    return decode(row, slug, batch_id)


def list_batches(conn: Connection, slug: str) -> list[dict[str, Any]]:
    org = organization(conn, slug)
    rows = (
        conn.execute(
            select(batches.c.batch_id, batches.c.revision, batches.c.state)
            .where(batches.c.organization_id == org)
            .order_by(batches.c.updated_at.desc())
            .limit(20)
        )
        .mappings()
        .all()
    )
    summaries = []
    for row in rows:
        item = decode(row, slug, row["batch_id"])
        state = item["state"]
        summaries.append(
            {
                key: state[key]
                for key in (
                    "id",
                    "target",
                    "status",
                    "cursor",
                    "provider_attempts",
                    "resume_at",
                    "notice",
                )
            }
            | {
                "revision": item["revision"],
                "count": len(state["candidates"]),
                "query_count": len(state["queries"]),
            }
        )
    return summaries


def create_batch(
    conn: Connection, slug: str, location: str, scope: Scope, target: int
) -> StateSnapshot:
    org = organization(conn, slug, lock=True)
    if (
        len(
            conn.execute(
                select(batches.c.batch_id).where(batches.c.organization_id == org).limit(20)
            ).all()
        )
        >= 20
    ):
        raise BatchCapacity()
    batch_id = str(uuid.uuid4())
    queries = [
        BatchQuery(
            role=role,
            scope=scope,
            query=f"{location.strip()} {label} {sector} public business profile",
        )
        for role, label in ROLES.items()
        for sector in SECTORS
    ]
    state = ResearchBatch(id=batch_id, tenant_id=slug, target=target, queries=queries)
    conn.execute(
        insert(batches).values(
            organization_id=org,
            batch_id=batch_id,
            revision=1,
            state=state.model_dump(mode="json"),
            updated_at=datetime.now(UTC),
        )
    )
    return {"revision": 1, "state": state.model_dump(mode="json")}


def write_batch(
    conn: Connection, slug: str, batch_id: str, revision: int, state: object
) -> StateSnapshot:
    state = ResearchBatch.model_validate(state)
    if state.tenant_id != slug or state.id != batch_id:
        raise ValueError("Batch identity mismatch")
    org = organization(conn, slug)
    changed = conn.execute(
        update(batches)
        .where(
            batches.c.organization_id == org,
            batches.c.batch_id == batch_id,
            batches.c.revision == revision,
        )
        .values(
            revision=revision + 1, state=state.model_dump(mode="json"), updated_at=datetime.now(UTC)
        )
    )
    if changed.rowcount != 1:
        raise RevisionConflict()
    return {"revision": revision + 1, "state": state.model_dump(mode="json")}


def change_batch(
    conn: Connection,
    slug: str,
    batch_id: str,
    revision: int,
    action: Literal["pause", "resume", "cancel", "skip_uncertain"],
) -> StateSnapshot:
    current = read_batch(conn, slug, batch_id)
    if current["revision"] != revision:
        raise RevisionConflict()
    state = transition(ResearchBatch.model_validate(current["state"]), slug, action)
    return write_batch(conn, slug, batch_id, revision, state)


def lock_id(slug: str, batch_id: str) -> int:
    return int.from_bytes(sha256((slug + "|" + batch_id).encode()).digest()[:8], "big", signed=True)


def make_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        poolclass=NullPool,
        echo=False,
        hide_parameters=True,
        connect_args={"timeout": 8, "command_timeout": 12},
    )


async def advance_locked(
    conn: AsyncConnection,
    settings: Settings,
    slug: str,
    batch_id: str,
    revision: int,
    action: BatchMutation = "advance",
) -> StateSnapshot:
    """A PostgreSQL session advisory lock survives checkpoint commits."""
    token = lock_id(slug, batch_id)
    acquired = False
    try:
        acquired = bool(
            await conn.scalar(text("SELECT pg_try_advisory_lock(:token)"), {"token": token})
        )
        await conn.commit()
        if not acquired:
            raise BatchBusy()
        current = await conn.run_sync(lambda c: read_batch(c, slug, batch_id))
        await conn.commit()
        if current["revision"] != revision:
            raise RevisionConflict()

        async def checkpoint(state: dict[str, Any]) -> None:
            nonlocal current
            try:
                saved = await conn.run_sync(
                    lambda c: write_batch(c, slug, batch_id, current["revision"], state)
                )
                await conn.commit()
                current = saved
            except BaseException:
                await conn.rollback()
                raise

        if action == "advance":
            await advance_batch(
                ResearchBatch.model_validate(current["state"]), settings, slug, checkpoint
            )
        else:
            await checkpoint(
                transition(ResearchBatch.model_validate(current["state"]), slug, action).model_dump(
                    mode="json"
                )
            )
        return current
    finally:
        if acquired:
            # Any failed request rolls back before releasing the session lock.
            try:
                await conn.rollback()
                await conn.execute(text("SELECT pg_advisory_unlock(:token)"), {"token": token})
                await conn.commit()
            except BaseException:
                # A broken session must close, rather than returning a held lock.
                await conn.invalidate()


async def access_batches(
    settings: Settings,
    slug: str,
    operation: str = "list",
    batch_id: str | None = None,
    revision: int | None = None,
    body: BatchCreation | None = None,
) -> list[dict[str, Any]] | StateSnapshot:
    engine = make_engine(settings)
    try:
        if operation in {"advance", "pause", "resume", "cancel", "skip_uncertain"}:
            if batch_id is None or revision is None:
                raise ValueError("Batch identity and revision required")
            async with engine.connect() as conn:
                return await advance_locked(
                    conn, settings, slug, batch_id, revision, cast(BatchMutation, operation)
                )
        async with engine.begin() as conn:
            if operation == "list":
                return await conn.run_sync(lambda c: list_batches(c, slug))
            if operation == "read":
                if batch_id is None:
                    raise ValueError("Batch identity required")
                return await conn.run_sync(lambda c: read_batch(c, slug, batch_id))
            if operation == "create":
                if body is None:
                    raise ValueError("Batch creation body required")
                return await conn.run_sync(
                    lambda c: create_batch(c, slug, body.location, body.scope, body.target)
                )
            raise ValueError("Unknown batch operation")
    finally:
        await engine.dispose()


def initialize(conn: Connection, slug: str) -> None:
    organization(conn, slug)
    batches.create(conn, checkfirst=True)
    if {col["name"] for col in inspect(conn).get_columns(batches.name)} != {
        "organization_id",
        "batch_id",
        "revision",
        "state",
        "updated_at",
    }:
        raise ValueError("Unexpected research batch table schema")
    list_batches(conn, slug)


async def provision() -> None:
    from core.config.settings import Settings

    settings = Settings()
    if (
        not settings.is_dev_like
        or not settings.enable_dev_routes
        or not settings.prospect_storage_enabled
    ):
        raise ValueError("Local research storage must be enabled")
    engine = make_engine(settings)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: initialize(c, settings.default_tenant_id))
        print(
            "PASS: Dedicated research-batch table ready. Existing workspace and prospect records preserved."
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(provision())
    except Exception:
        raise SystemExit(
            "Research-batch database setup needs attention. No credentials displayed."
        ) from None
