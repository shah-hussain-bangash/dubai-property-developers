"""Authenticated PostgreSQL background-job processor.

Development-only: not connected to the deployed Docker worker.

Security and ownership:
- Authenticate the original encrypted job publication.
- Validate PostgreSQL registration.
- Claim an exclusive processing lease.
- Renew that lease during handler execution.
- Never mark a lost lease as an ordinary handler failure.

Redis reservation reconciliation and recovery are separate concerns.
External actions still require idempotency protection.
"""

from __future__ import annotations

from typing import Any

from apps.worker.jobs.envelope import JobEnvelope, acknowledge_job
from apps.worker.jobs.lease_heartbeat import (
    LeaseHeartbeatLost,
    run_with_lease_heartbeat,
)
from apps.worker.jobs.payload_auth import (
    JobPayloadAuthenticationError,
    PostgresJobPayloadAuthenticator,
)
from apps.worker.tasks.handlers import get_handler
from database.repositories.postgres_background_job_store import (
    PostgresBackgroundJobStore,
)


async def process_postgres_job(
    runtime: Any,
    redis: Any,
    raw: str,
    store: PostgresBackgroundJobStore,
    *,
    authenticator: PostgresJobPayloadAuthenticator,
    worker_id: str,
    lease_seconds: int = 120,
    retry_delay_seconds: int = 30,
    heartbeat_interval_seconds: float | None = None,
) -> str:
    """Process one Redis reservation under PostgreSQL ownership.

    Returns:
        succeeded: DB completed, Redis acknowledged
        failed: handler failure recorded in DB
        duplicate: terminal DB job acknowledged
        deferred: another owner or retry is not yet eligible

    Lease loss and infrastructure errors propagate. Failed and
    deferred Redis reservations remain for future reconciliation.
    """

    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")

    if authenticator is None:
        raise ValueError("Payload authenticator is required")

    received_job = JobEnvelope.model_validate_json(raw)

    authenticated_job = await authenticator.authenticate(received_job)

    if not isinstance(authenticated_job, JobEnvelope) or authenticated_job != received_job:
        raise JobPayloadAuthenticationError("Authenticated job does not match Redis delivery")

    job = authenticated_job

    record = await store.get(job.tenant_id, job.job_id)

    if record is None:
        raise RuntimeError("Unregistered job; refusing handler execution")

    if record.job_type != job.job_type or record.max_attempts != job.max_attempts:
        raise RuntimeError("Job identity differs from PostgreSQL registration")

    if record.status in {"succeeded", "failed"}:
        acknowledged = await acknowledge_job(redis, raw)

        if not acknowledged:
            raise RuntimeError("Terminal job reservation was not found")

        return "duplicate"

    token = await store.claim(
        job.tenant_id,
        job.job_id,
        worker_id,
        lease_seconds=lease_seconds,
    )

    if token is None:
        return "deferred"

    try:
        handler = get_handler(job.job_type)

        await run_with_lease_heartbeat(
            handler(runtime, job),
            store=store,
            tenant_id=job.tenant_id,
            job_id=job.job_id,
            worker_id=worker_id,
            lease_token=token,
            lease_seconds=lease_seconds,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
        )

    except LeaseHeartbeatLost:
        # Do not call store.fail() after ownership becomes uncertain.
        # Do not acknowledge the Redis reservation.
        # Recovery must reconcile this job later.
        raise

    except Exception:
        status = await store.fail(
            job.tenant_id,
            job.job_id,
            worker_id,
            token,
            retry_delay_seconds=retry_delay_seconds,
            error_code="handler_error",
        )

        if status is None:
            raise RuntimeError("Job failure could not be recorded; lease may be lost") from None

        return "failed"

    completed = await store.complete(
        job.tenant_id,
        job.job_id,
        worker_id,
        token,
    )

    if not completed:
        raise RuntimeError("Job execution finished but completion lease is no longer valid")

    acknowledged = await acknowledge_job(redis, raw)

    if not acknowledged:
        raise RuntimeError("PostgreSQL recorded success but Redis reservation was not found")

    return "succeeded"
