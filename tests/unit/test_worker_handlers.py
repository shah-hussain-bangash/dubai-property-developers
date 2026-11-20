"""Unit tests for background-job handler behavior.

Uses mocked workflows and does not access PostgreSQL,
Redis, CRM, WhatsApp or external services.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.worker.jobs.envelope import JobEnvelope
from apps.worker.tasks.handlers import followup_scan


@pytest.mark.asyncio
async def test_failed_followup_workflow_raises_error():
    """A failed workflow must not be treated as a successful job."""

    job = JobEnvelope(
        job_type="followup.scan",
        tenant_id="demo-org",
        payload={"tasks": []},
        correlation_id="test-failed-followup",
    )

    run = SimpleNamespace(
        execution_id="fictional-execution-001",
        status=SimpleNamespace(value="failed"),
    )

    runner = SimpleNamespace(run=AsyncMock(return_value=(run, None)))

    runtime = SimpleNamespace(runner=runner)

    with pytest.raises(
        RuntimeError,
        match="Follow-up workflow did not complete successfully",
    ):
        await followup_scan(runtime, job)

    runner.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_successful_followup_workflow_returns_result():
    """Successful workflows should return their execution details."""

    job = JobEnvelope(
        job_type="followup.scan",
        tenant_id="demo-org",
        payload={"tasks": []},
        correlation_id="test-successful-followup",
    )

    run = SimpleNamespace(
        execution_id="fictional-execution-002",
        status=SimpleNamespace(value="succeeded"),
    )

    runner = SimpleNamespace(run=AsyncMock(return_value=(run, None)))

    runtime = SimpleNamespace(runner=runner)

    result = await followup_scan(runtime, job)

    assert result == {
        "execution_id": "fictional-execution-002",
        "status": "succeeded",
    }

    runner.run.assert_awaited_once()
