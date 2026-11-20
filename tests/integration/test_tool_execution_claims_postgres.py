"""Isolated PostgreSQL integration tests for tool execution claims.

Only runs with RUN_EXECUTION_LEDGER_DB_TESTS=1.
All writes are restricted to the dubai_ai_test database.
Does not execute external tools or modify active workers.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config.settings import get_settings
from database.models.identity import Organization
from database.models.tool_execution import ToolExecutionLedger
from database.repositories.tool_execution_claims import (
    PostgresToolExecutionClaimStore,
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_EXECUTION_LEDGER_DB_TESTS") != "1",
        reason="Set RUN_EXECUTION_LEDGER_DB_TESTS=1 to run isolated ledger tests",
    ),
]


@pytest.fixture
async def ledger_environment() -> AsyncIterator[
    tuple[PostgresToolExecutionClaimStore, str, str]
]:
    application_url = make_url(
        get_settings().database_url.get_secret_value()
    )

    if application_url.database != "dubai_ai":
        raise RuntimeError("Unexpected configured application database")

    test_url = application_url.set(database="dubai_ai_test")

    engine = create_async_engine(
        test_url,
        pool_pre_ping=True,
    )

    factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        autoflush=False,
    )

    first_id = uuid.uuid4()
    second_id = uuid.uuid4()

    first_tenant = f"ledger-test-{first_id.hex[:16]}"
    second_tenant = f"ledger-test-{second_id.hex[:16]}"

    created = False

    try:
        async with engine.connect() as connection:
            database_name = await connection.scalar(
                text("SELECT current_database()")
            )

            if database_name != "dubai_ai_test":
                raise RuntimeError(
                    f"Unsafe test database: {database_name}"
                )

            version = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )

            if version != "0008_tool_request_fingerprint":
                raise RuntimeError(
                    f"Unexpected test database revision: {version}"
                )

        async with factory() as session:
            async with session.begin():
                session.add_all(
                    [
                        Organization(
                            id=first_id,
                            name="Temporary Ledger Test A",
                            slug=first_tenant,
                            is_active=True,
                        ),
                        Organization(
                            id=second_id,
                            name="Temporary Ledger Test B",
                            slug=second_tenant,
                            is_active=True,
                        ),
                    ]
                )

        created = True

        yield (
            PostgresToolExecutionClaimStore(factory),
            first_tenant,
            second_tenant,
        )

    finally:
        try:
            if created:
                async with factory() as session:
                    async with session.begin():
                        await session.execute(
                            delete(ToolExecutionLedger).where(
                                ToolExecutionLedger.organization_id.in_(
                                    [first_id, second_id]
                                )
                            )
                        )

                        await session.execute(
                            delete(Organization).where(
                                Organization.id.in_(
                                    [first_id, second_id]
                                )
                            )
                        )
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_postgres_claim_has_one_owner(
    ledger_environment,
) -> None:
    store, tenant, _ = ledger_environment
    key = f"test:concurrent:{uuid.uuid4().hex}"

    results = await asyncio.wait_for(
        asyncio.gather(
            *(
                store.claim(tenant, key, "test.send", request_fingerprint=make_request_fingerprint(tenant, "test.send", {}))
                for _ in range(10)
            )
        ),
        timeout=20,
    )

    owners = [owner for owner in results if owner is not None]

    assert len(owners) == 1

    record = await store.get(tenant, key)

    assert record is not None
    assert record.state == "in_progress"
    assert record.owner_token == owners[0]


@pytest.mark.asyncio
async def test_wrong_owner_cannot_complete(
    ledger_environment,
) -> None:
    store, tenant, _ = ledger_environment
    key = f"test:ownership:{uuid.uuid4().hex}"

    owner = await store.claim(tenant, key, "test.send", request_fingerprint=make_request_fingerprint(tenant, "test.send", {}))
    assert owner is not None

    assert await store.complete(
        tenant,
        key,
        "incorrect-owner",
        {"message_id": "wrong"},
    ) is False

    assert await store.complete(
        tenant,
        key,
        owner,
        {"message_id": "correct"},
    ) is True

    record = await store.get(tenant, key)

    assert record is not None
    assert record.state == "completed"
    assert record.result_json == {"message_id": "correct"}

    assert await store.claim(tenant, key, "test.send", request_fingerprint=make_request_fingerprint(tenant, "test.send", {})) is None


@pytest.mark.asyncio
async def test_tenants_are_isolated(
    ledger_environment,
) -> None:
    store, first_tenant, second_tenant = ledger_environment
    key = f"test:shared-key:{uuid.uuid4().hex}"

    first_owner = await store.claim(
        first_tenant, key, "test.send"
    , request_fingerprint=make_request_fingerprint(first_tenant, "test.send", {}))

    second_owner = await store.claim(
        second_tenant, key, "test.send"
    , request_fingerprint=make_request_fingerprint(second_tenant, "test.send", {}))

    assert first_owner is not None
    assert second_owner is not None
    assert first_owner != second_owner

    assert await store.complete(
        second_tenant,
        key,
        first_owner,
        {"message_id": "invalid"},
    ) is False

    first = await store.get(first_tenant, key)
    second = await store.get(second_tenant, key)

    assert first is not None
    assert second is not None
    assert first.organization_id != second.organization_id


@pytest.mark.asyncio
async def test_uncertain_claim_cannot_be_reclaimed(
    ledger_environment,
) -> None:
    store, tenant, _ = ledger_environment
    key = f"test:uncertain:{uuid.uuid4().hex}"

    owner = await store.claim(tenant, key, "test.send", request_fingerprint=make_request_fingerprint(tenant, "test.send", {}))
    assert owner is not None

    assert await store.mark_uncertain(
        tenant, key, owner
    ) is True

    assert await store.claim(tenant, key, "test.send", request_fingerprint=make_request_fingerprint(tenant, "test.send", {})) is None

    assert await store.complete(
        tenant,
        key,
        owner,
        {"message_id": "late"},
    ) is False

    record = await store.get(tenant, key)
    assert record is not None
    assert record.state == "uncertain"


@pytest.mark.asyncio
async def test_claim_persists_across_sessions(
    ledger_environment,
) -> None:
    store, tenant, _ = ledger_environment
    key = f"test:persist:{uuid.uuid4().hex}"

    owner = await store.claim(tenant, key, "test.send", request_fingerprint=make_request_fingerprint(tenant, "test.send", {}))
    assert owner is not None

    # Each repository method opens and closes its own session.
    first = await store.get(tenant, key)
    second = await store.get(tenant, key)

    assert first is not None
    assert second is not None
    assert second.owner_token == owner

    assert await store.complete(
        tenant,
        key,
        owner,
        {"message_id": "persisted"},
    ) is True

    completed = await store.get(tenant, key)

    assert completed is not None
    assert completed.state == "completed"
    assert completed.result_json == {
        "message_id": "persisted"
    }

# Step 272: PostgreSQL-backed coordinator integration tests

from core.resilience.tool_execution_coordinator import (
    CoordinationStatus,
    ExecutionOutcomeUncertain,
    ToolExecutionCoordinator,
)


@pytest.mark.asyncio
async def test_two_coordinators_share_postgres_claim(
    ledger_environment,
) -> None:
    store, tenant, _ = ledger_environment

    coordinator_a = ToolExecutionCoordinator(store)
    coordinator_b = ToolExecutionCoordinator(store)

    key = f"test:coordinator-concurrent:{uuid.uuid4().hex}"

    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def external_action() -> dict[str, str]:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"message_id": "postgres-message-1"}

    first_task = asyncio.create_task(
        coordinator_a.execute(
            tenant, key, "test.send", external_action
        , payload={})
    )

    try:
        await asyncio.wait_for(started.wait(), timeout=10)

        second = await asyncio.wait_for(
            coordinator_b.execute(
                tenant, key, "test.send", external_action
            , payload={}),
            timeout=10,
        )

        assert second.status == CoordinationStatus.IN_PROGRESS
        assert calls == 1

    finally:
        release.set()

    first = await asyncio.wait_for(first_task, timeout=10)

    assert first.status == CoordinationStatus.EXECUTED
    assert calls == 1

    replay = await coordinator_b.execute(
        tenant, key, "test.send", external_action
    , payload={})

    assert replay.status == CoordinationStatus.REPLAYED
    assert replay.data == {"message_id": "postgres-message-1"}
    assert calls == 1

    record = await store.get(tenant, key)

    assert record is not None
    assert record.state == "completed"


@pytest.mark.asyncio
async def test_postgres_coordinator_uncertain_prevents_retry(
    ledger_environment,
) -> None:
    store, tenant, _ = ledger_environment

    coordinator_a = ToolExecutionCoordinator(store)
    coordinator_b = ToolExecutionCoordinator(store)

    key = f"test:coordinator-uncertain:{uuid.uuid4().hex}"

    calls = 0

    async def failing_action() -> dict[str, str]:
        nonlocal calls
        calls += 1
        raise RuntimeError("Simulated ambiguous provider failure")

    with pytest.raises(ExecutionOutcomeUncertain):
        await coordinator_a.execute(
            tenant, key, "test.send", failing_action
        , payload={})

    record = await store.get(tenant, key)

    assert record is not None
    assert record.state == "uncertain"

    second = await coordinator_b.execute(
        tenant, key, "test.send", failing_action
    , payload={})

    assert second.status == CoordinationStatus.UNCERTAIN
    assert calls == 1

@pytest.mark.asyncio
async def test_reused_key_cannot_replay_another_tool(
    ledger_environment,
) -> None:
    store, tenant, _ = ledger_environment

    coordinator = ToolExecutionCoordinator(store)
    key = f"test:tool-mismatch:{uuid.uuid4().hex}"

    calls = 0

    async def action() -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"message_id": "original-result"}

    original = await coordinator.execute(
        tenant,
        key,
        "crm.create_lead",
        action,
     payload={})

    assert original.status == CoordinationStatus.EXECUTED
    assert calls == 1

    record = await store.get(tenant, key)
    assert record is not None
    assert record.tool_name == "crm.create_lead"

    with pytest.raises(
        ExecutionOutcomeUncertain,
        match="(?i)(tool|identity|mismatch)",
    ):
        await coordinator.execute(
            tenant,
            key,
            "whatsapp.send_message",
            action,
         payload={})

    assert calls == 1

@pytest.mark.asyncio
async def test_request_fingerprint_persisted_in_postgres(
    ledger_environment,
) -> None:
    from core.resilience.request_fingerprint import (
        make_request_fingerprint,
    )

    store, tenant, _ = ledger_environment

    key = f"test:fingerprint:{uuid.uuid4().hex}"
    tool = "crm.create_lead"
    payload = {
        "name": "Test Lead",
        "budget": 1000000,
    }

    fingerprint = make_request_fingerprint(
        tenant, tool, payload
    )

    owner = await store.claim(
        tenant,
        key,
        tool,
        request_fingerprint=fingerprint,
    )

    assert owner is not None

    record = await store.get(tenant, key)

    assert record is not None
    assert record.tool_name == tool
    assert record.request_fingerprint == fingerprint
    assert record.state == "in_progress"

    duplicate = await store.claim(
        tenant,
        key,
        tool,
        request_fingerprint=fingerprint,
    )

    assert duplicate is None

    unchanged = await store.get(tenant, key)

    assert unchanged is not None
    assert unchanged.request_fingerprint == fingerprint

@pytest.mark.asyncio
async def test_same_tool_key_changed_payload_must_be_rejected(
    ledger_environment,
) -> None:
    store, tenant, _ = ledger_environment

    coordinator = ToolExecutionCoordinator(store)
    key = f"test:payload-mismatch:{uuid.uuid4().hex}"
    calls = 0

    async def action() -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"message_id": f"message-{calls}"}

    first = await coordinator.execute(
        tenant,
        key,
        "whatsapp.send_message",
        action,
        payload={
            "recipient": "+971500000000",
            "message": "First message",
        },
    )

    assert first.status == CoordinationStatus.EXECUTED

    with pytest.raises(
        ExecutionOutcomeUncertain,
        match="(?i)(fingerprint|payload|identity|mismatch)",
    ):
        await coordinator.execute(
            tenant,
            key,
            "whatsapp.send_message",
            action,
            payload={
                "recipient": "+971500000000",
                "message": "Different message",
            },
        )

    assert calls == 1

@pytest.mark.asyncio
async def test_missing_request_fingerprint_is_rejected(
    ledger_environment,
) -> None:
    store, tenant, _ = ledger_environment

    key = f"test:missing-fingerprint:{uuid.uuid4().hex}"

    with pytest.raises(
        (TypeError, ValueError),
        match="(?i)(fingerprint|missing)",
    ):
        await store.claim(
            tenant,
            key,
            "crm.create_lead",
        )

    record = await store.get(tenant, key)
    assert record is None

from core.resilience.request_fingerprint import make_request_fingerprint

@pytest.mark.asyncio
async def test_identical_request_replays_persisted_result(
    ledger_environment,
) -> None:
    store, tenant, _ = ledger_environment

    coordinator_a = ToolExecutionCoordinator(store)
    coordinator_b = ToolExecutionCoordinator(store)

    key = f"test:identical-replay:{uuid.uuid4().hex}"
    calls = 0

    async def action() -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"message_id": f"message-{calls}"}

    payload_a = {
        "recipient": "+971500000000",
        "message": "Hello",
    }

    payload_b = {
        "message": "Hello",
        "recipient": "+971500000000",
    }

    first = await coordinator_a.execute(
        tenant,
        key,
        "whatsapp.send_message",
        action,
        payload=payload_a,
    )

    second = await coordinator_b.execute(
        tenant,
        key,
        "whatsapp.send_message",
        action,
        payload=payload_b,
    )

    assert first.status == CoordinationStatus.EXECUTED
    assert second.status == CoordinationStatus.REPLAYED
    assert first.data == second.data
    assert calls == 1

    record = await store.get(tenant, key)

    assert record is not None
    assert record.state == "completed"

    assert record.request_fingerprint == (
        make_request_fingerprint(
            tenant,
            "whatsapp.send_message",
            payload_a,
        )
    )

@pytest.mark.asyncio
async def test_reconciliation_lists_only_unresolved_claims(
    ledger_environment,
) -> None:
    store, tenant, _ = ledger_environment

    prefix = f"reconcile:{uuid.uuid4().hex}"
    tool = "crm.create_lead"
    fingerprint = make_request_fingerprint(
        tenant, tool, {"name": "Reconciliation Test"}
    )

    pending_key = f"{prefix}:pending"
    uncertain_key = f"{prefix}:uncertain"
    completed_key = f"{prefix}:completed"

    pending_owner = await store.claim(
        tenant, pending_key, tool, fingerprint
    )
    uncertain_owner = await store.claim(
        tenant, uncertain_key, tool, fingerprint
    )
    completed_owner = await store.claim(
        tenant, completed_key, tool, fingerprint
    )

    assert pending_owner is not None
    assert uncertain_owner is not None
    assert completed_owner is not None

    assert await store.mark_uncertain(
        tenant, uncertain_key, uncertain_owner
    )
    assert await store.complete(
        tenant,
        completed_key,
        completed_owner,
        {"lead_id": "completed-lead"},
    )

    records = await store.list_unresolved(tenant, limit=50)
    indexed = {
        record.idempotency_key: record
        for record in records
    }

    assert pending_key in indexed
    assert uncertain_key in indexed
    assert completed_key not in indexed

    assert indexed[pending_key].state == "in_progress"
    assert indexed[uncertain_key].state == "uncertain"

    # Discovery must not modify ownership or states.
    pending_after = await store.get(tenant, pending_key)
    uncertain_after = await store.get(tenant, uncertain_key)

    assert pending_after.owner_token == pending_owner
    assert pending_after.state == "in_progress"

    assert uncertain_after.owner_token == uncertain_owner
    assert uncertain_after.state == "uncertain"


@pytest.mark.asyncio
async def test_reconciliation_discovery_is_tenant_scoped(
    ledger_environment,
) -> None:
    store, first_tenant, second_tenant = ledger_environment

    key = f"reconcile:tenant:{uuid.uuid4().hex}"
    tool = "test.send"

    owner = await store.claim(
        first_tenant,
        key,
        tool,
        make_request_fingerprint(
            first_tenant, tool, {"message": "test"}
        ),
    )

    assert owner is not None

    first_records = await store.list_unresolved(
        first_tenant, limit=50
    )
    second_records = await store.list_unresolved(
        second_tenant, limit=50
    )

    assert any(
        record.idempotency_key == key
        for record in first_records
    )

    assert all(
        record.idempotency_key != key
        for record in second_records
    )

@pytest.mark.asyncio
async def test_reconciliation_rejects_invalid_inputs(
    ledger_environment,
) -> None:
    store, tenant, _ = ledger_environment

    # Invalid tenant identifiers must not reach an unrestricted query.
    for invalid_tenant in ("", "   "):
        with pytest.raises(ValueError):
            await store.list_unresolved(
                invalid_tenant, limit=10
            )

    # Reject unbounded, negative, Boolean, and non-integer limits.
    for invalid_limit in (0, -1, 101, True, False, 1.5, "10"):
        with pytest.raises(ValueError, match="limit"):
            await store.list_unresolved(
                tenant, limit=invalid_limit
            )


@pytest.mark.asyncio
async def test_reconciliation_limit_and_order_are_stable(
    ledger_environment,
) -> None:
    store, tenant, _ = ledger_environment

    tool = "crm.create_lead"
    fingerprint = make_request_fingerprint(
        tenant,
        tool,
        {"source": "reconciliation-limit-test"},
    )

    prefix = f"reconcile:ordering:{uuid.uuid4().hex}"

    keys = [
        f"{prefix}:first",
        f"{prefix}:second",
        f"{prefix}:third",
    ]

    for key in keys:
        owner = await store.claim(
            tenant, key, tool, fingerprint
        )
        assert owner is not None

    records = await store.list_unresolved(
        tenant, limit=2
    )

    assert len(records) == 2

    ordering = [
        (record.claimed_at, record.id)
        for record in records
    ]

    assert ordering == sorted(ordering)

    # Reading the same unchanged ledger should return
    # the same ordered records.
    repeated = await store.list_unresolved(
        tenant, limit=2
    )

    assert [record.id for record in records] == [
        record.id for record in repeated
    ]

    # The query must never modify these claims.
    for key in keys:
        record = await store.get(tenant, key)
        assert record is not None
        assert record.state == "in_progress"

@pytest.mark.asyncio
async def test_reconciliation_cursor_paginates_without_duplicates(
    ledger_environment,
) -> None:
    store, tenant, other_tenant = ledger_environment

    tool = "crm.create_lead"
    payload = {"source": "cursor-pagination-test"}
    fingerprint = make_request_fingerprint(
        tenant, tool, payload
    )

    prefix = f"reconcile:cursor:{uuid.uuid4().hex}"

    keys = [
        f"{prefix}:{number}"
        for number in range(5)
    ]

    for key in keys:
        owner = await store.claim(
            tenant, key, tool, fingerprint
        )
        assert owner is not None

    all_records = []
    cursor = None

    for page_number in range(4):
        page = await store.list_unresolved(
            tenant,
            limit=2,
            after=cursor,
        )

        if not page:
            break

        assert len(page) <= 2

        all_records.extend(page)

        last = page[-1]
        cursor = (last.claimed_at, last.id)

    returned_keys = [
        record.idempotency_key
        for record in all_records
    ]

    assert len(returned_keys) == 5
    assert len(set(returned_keys)) == 5
    assert set(returned_keys) == set(keys)

    ordering = [
        (record.claimed_at, record.id)
        for record in all_records
    ]
    assert ordering == sorted(ordering)

    # The same cursor must not expose another tenant's claims.
    other_page = await store.list_unresolved(
        other_tenant,
        limit=2,
        after=cursor,
    )

    assert all(
        record.idempotency_key not in keys
        for record in other_page
    )

    # Pagination must not change states or ownership.
    for key in keys:
        record = await store.get(tenant, key)
        assert record is not None
        assert record.state == "in_progress"

@pytest.mark.asyncio
async def test_reconciliation_rejects_invalid_cursors(
    ledger_environment,
) -> None:
    from datetime import datetime, UTC
    from uuid import uuid4

    store, tenant, _ = ledger_environment

    invalid_cursors = [
        (),
        ("invalid", "cursor"),
        (datetime.now(UTC),),
        (datetime.now(UTC), "not-a-uuid"),
        (datetime.now(UTC).replace(tzinfo=None), uuid4()),
        (None, uuid4()),
        [datetime.now(UTC), uuid4()],
        "invalid-cursor",
        123,
    ]

    for cursor in invalid_cursors:
        with pytest.raises(ValueError, match="after"):
            await store.list_unresolved(
                tenant,
                limit=10,
                after=cursor,
            )


@pytest.mark.asyncio
async def test_reconciliation_handles_state_changes_between_pages(
    ledger_environment,
) -> None:
    store, tenant, _ = ledger_environment

    tool = "crm.create_lead"
    payload = {"source": "state-change-pagination-test"}
    fingerprint = make_request_fingerprint(
        tenant, tool, payload
    )

    prefix = f"reconcile:state-change:{uuid.uuid4().hex}"

    keys = [
        f"{prefix}:first",
        f"{prefix}:second",
        f"{prefix}:third",
    ]

    owners = []

    for key in keys:
        owner = await store.claim(
            tenant,
            key,
            tool,
            fingerprint,
        )
        assert owner is not None
        owners.append(owner)

    first_page = await store.list_unresolved(
        tenant,
        limit=1,
    )

    assert len(first_page) == 1
    assert first_page[0].idempotency_key == keys[0]

    cursor = (
        first_page[-1].claimed_at,
        first_page[-1].id,
    )

    # One claim completes after page one is read.
    assert await store.complete(
        tenant,
        keys[1],
        owners[1],
        {"lead_id": "completed-lead"},
    )

    # Another claim changes from in_progress to uncertain.
    assert await store.mark_uncertain(
        tenant,
        keys[2],
        owners[2],
    )

    second_page = await store.list_unresolved(
        tenant,
        limit=10,
        after=cursor,
    )

    returned_keys = {
        record.idempotency_key
        for record in second_page
    }

    assert keys[0] not in returned_keys
    assert keys[1] not in returned_keys
    assert keys[2] in returned_keys

    third_record = await store.get(tenant, keys[2])

    assert third_record is not None
    assert third_record.state == "uncertain"

    # Reconciliation discovery must not change ownership.
    assert third_record.owner_token == owners[2]
