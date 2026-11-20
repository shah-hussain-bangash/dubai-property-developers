
"""PostgreSQL integration tests for workflow execution history.

Tests:
- Save and retrieve workflow executions
- Update execution status and steps
- Enforce tenant isolation
- Exclude sensitive workflow state

Only runs when RUN_INTEGRATION_TESTS=1.
All test records are removed afterward.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config.settings import get_settings
from database.models.agent import WorkflowExecution
from database.models.identity import Organization
from database.repositories.postgres_workflow_run_store import (
    PostgresWorkflowRunStore,
)
from database.sessions.engine import create_engine, create_session_factory
from tests.factories import integration_enabled
from workflows.engine.core import (
    StepRecord,
    WorkflowRun,
    WorkflowStatus,
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not integration_enabled(),
        reason="Set RUN_INTEGRATION_TESTS=1",
    ),
]

ORG_A = "demo-org"
ORG_B = "tenant-isolation-test"


@pytest.fixture
async def workflow_store_context() -> AsyncIterator[tuple]:
    """Create a database-backed store with safe cleanup."""

    settings = get_settings()

    if not settings.is_dev_like:
        pytest.skip("Integration tests require development environment")

    engine = create_engine(settings)
    factory = create_session_factory(engine)
    store = PostgresWorkflowRunStore(factory)

    created_ids: list[uuid.UUID] = []

    try:
        # Verify both test organizations already exist.
        async with factory() as session:
            organizations = (
                await session.scalars(
                    select(Organization.slug).where(
                        Organization.slug.in_([ORG_A, ORG_B]),
                        Organization.is_active.is_(True),
                    )
                )
            ).all()

            if set(organizations) != {ORG_A, ORG_B}:
                pytest.skip(
                    "Required test organizations are missing"
                )

        yield store, factory, created_ids

    finally:
        try:
            if created_ids:
                async with factory() as session:
                    async with session.begin():
                        await session.execute(
                            delete(WorkflowExecution).where(
                                WorkflowExecution.id.in_(created_ids)
                            )
                        )
        finally:
            await engine.dispose()


def new_workflow(
    created_ids: list[uuid.UUID],
    tenant_id: str = ORG_A,
) -> WorkflowRun:
    execution_id = uuid.uuid4()
    created_ids.append(execution_id)

    return WorkflowRun(
        execution_id=execution_id.hex,
        workflow_id="lead_processing",
        tenant_id=tenant_id,
        correlation_id=f"test-{execution_id.hex[:16]}",
        status=WorkflowStatus.SUCCEEDED,
        current_step="store_in_crm",
        steps=[
            StepRecord(
                name="validate_normalize_deduplicate",
                outcome="continue",
                duration_ms=15,
            ),
            StepRecord(
                name="duplicate_gate",
                outcome="continue",
                duration_ms=2,
            ),
            StepRecord(
                name="store_in_crm",
                outcome="continue",
                duration_ms=30,
            ),
        ],
        finished_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_save_and_retrieve_workflow(
    workflow_store_context,
) -> None:
    store, factory, created_ids = workflow_store_context

    run = new_workflow(created_ids)

    await store.save(run)

    saved = await store.get(ORG_A, run.execution_id)

    assert saved is not None
    assert saved.id == uuid.UUID(run.execution_id)
    assert saved.workflow_key == "lead_processing"
    assert saved.status == "succeeded"
    assert saved.correlation_id == run.correlation_id
    assert saved.state["step_count"] == 3
    assert len(saved.state["steps"]) == 3
    assert saved.finished_at is not None


@pytest.mark.asyncio
async def test_update_workflow_status(
    workflow_store_context,
) -> None:
    store, factory, created_ids = workflow_store_context

    run = new_workflow(created_ids)

    run.status = WorkflowStatus.RUNNING
    run.finished_at = None

    await store.save(run)

    run.status = WorkflowStatus.FAILED
    run.current_step = "store_in_crm"
    run.finished_at = datetime.now(UTC)
    run.error = {
        "code": "workflow_error",
        "message": "Sensitive internal error information",
        "details": {},
    }

    run.steps.append(
        StepRecord(
            name="store_in_crm",
            outcome="failed",
            duration_ms=5,
            error_code="workflow_error",
        )
    )

    await store.save(run)

    saved = await store.get(ORG_A, run.execution_id)

    assert saved is not None
    assert saved.status == "failed"
    assert saved.error_code == "workflow_error"
    assert saved.error_message == "Workflow execution failed"
    assert saved.state["step_count"] == 4
    assert saved.finished_at is not None

    # An update must not create another execution.
    async with factory() as session:
        rows = (
            await session.scalars(
                select(WorkflowExecution).where(
                    WorkflowExecution.id == uuid.UUID(run.execution_id)
                )
            )
        ).all()

    assert len(rows) == 1


@pytest.mark.asyncio
async def test_tenant_isolation(
    workflow_store_context,
) -> None:
    store, factory, created_ids = workflow_store_context

    run = new_workflow(created_ids, ORG_A)

    await store.save(run)

    # The owning organization can retrieve the run.
    own_record = await store.get(ORG_A, run.execution_id)
    assert own_record is not None

    # Another organization cannot retrieve the run.
    other_record = await store.get(ORG_B, run.execution_id)
    assert other_record is None

    # Another organization cannot overwrite the run.
    forged = run.model_copy(deep=True)
    forged.tenant_id = ORG_B

    with pytest.raises(
        ValueError,
        match="another organization",
    ):
        await store.save(forged)

    # Verify the original record remains unchanged.
    original = await store.get(ORG_A, run.execution_id)

    assert original is not None
    assert original.status == "succeeded"


@pytest.mark.asyncio
async def test_sensitive_state_is_not_persisted(
    workflow_store_context,
) -> None:
    store, factory, created_ids = workflow_store_context

    run = new_workflow(created_ids)

    run.state = {
        "full_name": "Fictional Sensitive Customer",
        "email": "private-test@example.com",
        "phone": "+971500000001",
        "message": "Confidential fictional enquiry",
    }

    run.error = {
        "code": "test_error",
        "message": "Secret customer information",
        "details": {
            "email": "private-test@example.com",
        },
    }

    await store.save(run)

    saved = await store.get(ORG_A, run.execution_id)

    assert saved is not None

    # Only safe metadata should be stored.
    assert "full_name" not in saved.state
    assert "email" not in saved.state
    assert "phone" not in saved.state
    assert "message" not in saved.state

    assert saved.state["step_count"] == 3
    assert saved.error_code == "test_error"
    assert saved.error_message == "Workflow execution failed"

    assert "private-test@example.com" not in str(saved.state)
    assert "Secret customer" not in str(saved.state)
