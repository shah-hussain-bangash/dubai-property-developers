
"""Background job handlers.

Each handler receives the platform runtime and a validated job.

A handler must raise an exception when its intended operation
fails so that the worker can apply retry/dead-letter policies.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agents.base.context import ExecutionContext
from apps.worker.jobs.envelope import JobEnvelope
from core.exceptions.errors import NotFoundError
from knowledge.documents.models import SourceDocument
from workflows.followup_flow import (
    FOLLOWUP_AUTOMATION,
    FollowUpFlowState,
)
from workflows.runtime import PlatformRuntime


Handler = Callable[
    [PlatformRuntime, JobEnvelope],
    Awaitable[dict[str, Any]],
]


async def followup_scan(
    runtime: PlatformRuntime,
    job: JobEnvelope,
) -> dict[str, Any]:
    """Execute follow-up workflow and reject unsuccessful outcomes."""

    ctx = ExecutionContext.system(
        job.tenant_id,
        job.correlation_id,
    )

    run, _ = await runtime.runner.run(
        FOLLOWUP_AUTOMATION,
        FollowUpFlowState(request=job.payload),
        ctx,
    )

    # A completed Python call is not necessarily a successful
    # workflow. Reject failed or unfinished executions.
    if run.status.value != "succeeded":
        raise RuntimeError(
            "Follow-up workflow did not complete successfully"
        )

    return {
        "execution_id": run.execution_id,
        "status": run.status.value,
    }


async def ingest_document(
    runtime: PlatformRuntime,
    job: JobEnvelope,
) -> dict[str, Any]:
    """Validate and ingest a tenant-scoped knowledge document."""

    document = SourceDocument.model_validate(
        {
            **job.payload,
            "tenant_id": job.tenant_id,
        }
    )

    report = await runtime.ingestion.ingest(document)

    return {
        "document_id": report.document_id,
        "chunks": report.chunks,
    }


HANDLERS: dict[str, Handler] = {
    "followup.scan": followup_scan,
    "knowledge.ingest": ingest_document,
}


def get_handler(job_type: str) -> Handler:
    """Find the registered handler for a background job."""

    try:
        return HANDLERS[job_type]

    except KeyError as exc:
        raise NotFoundError(
            f"no handler for job type {job_type}"
        ) from exc
