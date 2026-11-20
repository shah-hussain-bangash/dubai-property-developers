from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from database.repositories.tool_execution_claims import (
    PostgresToolExecutionClaimStore,
)


def make_repository(
    scalar_result: object,
) -> tuple[PostgresToolExecutionClaimStore, MagicMock]:
    """Create a repository with a mocked database session."""

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(return_value=scalar_result)

    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=transaction)
    transaction.__aexit__ = AsyncMock(return_value=False)

    session.begin.return_value = transaction

    factory = MagicMock(return_value=session)
    repository = PostgresToolExecutionClaimStore(factory)

    repository._organization_id = AsyncMock(
        return_value=uuid.uuid4()
    )

    return repository, session


def compiled_sql(session: MagicMock) -> str:
    statement = session.scalar.call_args.args[0]
    return str(
        statement.compile(
            dialect=postgresql.dialect()
        )
    ).lower()


@pytest.mark.asyncio
async def test_claim_uses_atomic_postgres_insert() -> None:
    repository, session = make_repository(uuid.uuid4())

    owner = await repository.claim(
        "demo-org",
        "test:key-1",
        "test.send",
     request_fingerprint="a" * 64)

    assert owner is not None
    assert len(owner) == 32

    sql = compiled_sql(session)

    assert "insert into tool_execution_ledger" in sql
    assert "on conflict on constraint" in sql
    assert "uq_tool_execution_ledger_org_key" in sql
    assert "do nothing" in sql
    assert "returning" in sql


@pytest.mark.asyncio
async def test_duplicate_claim_returns_none() -> None:
    repository, session = make_repository(None)

    owner = await repository.claim(
        "demo-org",
        "test:key-1",
        "test.send",
     request_fingerprint="a" * 64)

    assert owner is None
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_completion_requires_owner_and_state() -> None:
    repository, session = make_repository(uuid.uuid4())

    completed = await repository.complete(
        "demo-org",
        "test:key-1",
        "owner-123",
        {"message_id": "123"},
    )

    assert completed is True

    statement = session.scalar.call_args.args[0]
    sql = compiled_sql(session)
    values = statement.compile(
        dialect=postgresql.dialect()
    ).params

    assert "update tool_execution_ledger" in sql
    assert "organization_id" in sql
    assert "idempotency_key" in sql
    assert "owner_token" in sql
    assert "state" in sql
    assert "completed" in values.values()
    assert "in_progress" in values.values()


@pytest.mark.asyncio
async def test_uncertain_transition_requires_owner() -> None:
    repository, session = make_repository(uuid.uuid4())

    changed = await repository.mark_uncertain(
        "demo-org",
        "test:key-1",
        "owner-123",
    )

    assert changed is True

    statement = session.scalar.call_args.args[0]
    sql = compiled_sql(session)
    values = statement.compile(
        dialect=postgresql.dialect()
    ).params

    assert "update tool_execution_ledger" in sql
    assert "organization_id" in sql
    assert "idempotency_key" in sql
    assert "owner_token" in sql
    assert "uncertain" in values.values()
    assert "in_progress" in values.values()


@pytest.mark.asyncio
async def test_invalid_claim_inputs_are_rejected() -> None:
    repository, session = make_repository(uuid.uuid4())

    with pytest.raises(ValueError):
        await repository.claim(
            "",
            "test:key-1",
            "test.send",
         request_fingerprint="a" * 64)

    with pytest.raises(ValueError):
        await repository.claim(
            "demo-org",
            "",
            "test.send",
         request_fingerprint="a" * 64)

    with pytest.raises(ValueError):
        await repository.claim(
            "demo-org",
            "test:key-1",
            "",
         request_fingerprint="a" * 64)

    session.scalar.assert_not_awaited()
