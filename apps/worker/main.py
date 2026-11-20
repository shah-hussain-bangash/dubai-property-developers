
"""Background worker using reliable Redis job reservations.

Run:
    python -m apps.worker.main

Features:
    - Atomic job reservation using BLMOVE
    - Explicit acknowledgement after success
    - Atomic retry transitions
    - Dead-letter routing
    - Malformed-job handling
    - Platform runtime cleanup

Future work:
    - Crash recovery and reservation leases
    - Delayed retries with backoff
    - Persistent job-status tracking
    - Job-level idempotency
"""

from __future__ import annotations

import asyncio
import signal
from typing import Any

from pydantic import ValidationError

from apps.worker.jobs.envelope import (
    JobEnvelope,
    QUEUE_KEY,
    acknowledge_job,
    reserve_job,
    transition_job,
)
from apps.worker.tasks.handlers import get_handler

from core.cache.redis import create_redis_client
from core.config.settings import get_settings
from core.observability.context import set_correlation_id
from core.observability.logging import configure_logging, get_logger

from workflows.runtime import PlatformRuntime, build_runtime


logger = get_logger("worker")


async def process_one(
    runtime: PlatformRuntime,
    raw: str,
    redis: Any | None = None,
) -> dict[str, Any] | None:
    """Process one reserved job.

    When redis is supplied, the raw job must already exist
    in the processing queue.

    Success:
        Execute handler and acknowledge reservation.

    Failure:
        Increment attempts and atomically move to retry
        queue or dead-letter queue.

    If the Redis acknowledgement or transition fails,
    allow the error to propagate. The original reservation
    is retained unless Redis has completed the transition.
    """

    try:
        job = JobEnvelope.model_validate_json(raw)

    except ValidationError:
        logger.error("discarding malformed job")

        if redis is not None:
            moved = await transition_job(
                redis,
                raw,
                raw,
                dead_letter=True,
            )

            if not moved:
                raise RuntimeError(
                    "Malformed job reservation was not found"
                )

        return None

    set_correlation_id(job.correlation_id)

    try:
        handler = get_handler(job.job_type)
        result = await handler(runtime, job)

    except Exception:
        job.attempts += 1

        logger.exception(
            "job failed",
            extra={
                "job_id": job.job_id,
                "attempts": job.attempts,
                "max_attempts": job.max_attempts,
            },
        )

        if redis is not None:
            exhausted = job.attempts >= job.max_attempts

            moved = await transition_job(
                redis,
                raw,
                job,
                dead_letter=exhausted,
            )

            if not moved:
                raise RuntimeError(
                    "Failed job reservation was not found"
                )

            if exhausted:
                logger.error(
                    "job moved to dead-letter queue",
                    extra={"job_id": job.job_id},
                )
            else:
                logger.info(
                    "job queued for retry",
                    extra={
                        "job_id": job.job_id,
                        "attempts": job.attempts,
                    },
                )

        return None

    # Handler completed successfully.
    # Do not acknowledge until handler execution has finished.
    if redis is not None:
        acknowledged = await acknowledge_job(redis, raw)

        if not acknowledged:
            raise RuntimeError(
                "Successful job reservation was not found"
            )

    logger.info(
        "job done",
        extra={
            "job_id": job.job_id,
            "job_type": job.job_type,
        },
    )

    return result


async def run_worker() -> None:
    """Start the Redis worker and process reserved jobs."""

    settings = get_settings()

    configure_logging(
        settings.log_level,
        json_output=settings.log_json,
    )

    runtime = build_runtime(settings)

    redis = None

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)

        except (NotImplementedError, RuntimeError):
            # Some Windows event loops do not support this.
            pass

    try:
        await runtime.initialize()

        redis = create_redis_client(settings)

        logger.info(
            "worker started",
            extra={"queue": QUEUE_KEY},
        )

        while not stop.is_set():

            raw = await reserve_job(
                redis,
                timeout=5,
            )

            if raw is None:
                continue

            await process_one(
                runtime,
                raw,
                redis,
            )

    finally:
        try:
            if redis is not None:
                await redis.aclose()

        finally:
            await runtime.shutdown()

        logger.info("worker stopped")


if __name__ == "__main__":
    try:
        asyncio.run(run_worker())

    except KeyboardInterrupt:
        pass
