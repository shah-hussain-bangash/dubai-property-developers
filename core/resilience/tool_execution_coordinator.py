"""Experimental durable tool execution coordinator.

Not connected to the production ToolGateway or workers.

Requires a claim store with PostgreSQL-style atomic claim,
get, complete and mark_uncertain operations.

Never automatically retries an action whose outcome is uncertain.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from core.resilience.request_fingerprint import make_request_fingerprint

logger = logging.getLogger(__name__)


class ClaimRecord(Protocol):
    state: str
    tool_name: str
    request_fingerprint: str | None
    result_json: dict[str, Any] | None


class ClaimRepository(Protocol):
    async def claim(
        self,
        tenant_id: str,
        key: str,
        tool_name: str,
        request_fingerprint: str,
    ) -> str | None: ...

    async def get(self, tenant_id: str, key: str) -> ClaimRecord | None: ...

    async def complete(
        self,
        tenant_id: str,
        key: str,
        owner_token: str,
        result: dict[str, Any],
    ) -> bool: ...

    async def mark_uncertain(
        self,
        tenant_id: str,
        key: str,
        owner_token: str,
    ) -> bool: ...


class CoordinationStatus(StrEnum):
    EXECUTED = "executed"
    REPLAYED = "replayed"
    IN_PROGRESS = "in_progress"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class CoordinationResult:
    status: CoordinationStatus
    data: dict[str, Any] | None = None


class ExecutionOutcomeUncertain(RuntimeError):
    """External execution or result persistence may be incomplete."""


class ToolExecutionCoordinator:
    """Coordinate one execution per tenant/key using durable claims.

    Authorization, tool allowlists, business validation, and human
    approvals must be enforced by the caller before calling execute().
    """

    def __init__(self, claims: ClaimRepository) -> None:
        self.claims = claims

    async def execute(
        self,
        tenant_id: str,
        key: str,
        tool_name: str,
        action: Callable[[], Awaitable[dict[str, Any]]],
        *,
        payload: dict[str, Any],
    ) -> CoordinationResult:
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not key or not key.strip():
            raise ValueError("idempotency key is required")
        if not tool_name or not tool_name.strip():
            raise ValueError("tool_name is required")

        fingerprint = make_request_fingerprint(tenant_id, tool_name, payload)

        owner = await self.claims.claim(tenant_id, key, tool_name, fingerprint)

        if owner is None:
            record = await self.claims.get(tenant_id, key)

            if record is None:
                raise ExecutionOutcomeUncertain(
                    "Claim exists or was observed concurrently, but its state cannot be verified"
                )

            if record.tool_name != tool_name:
                raise ExecutionOutcomeUncertain(
                    "Idempotency key tool identity mismatch: "
                    "existing claim belongs to a different tool"
                )

            if record.request_fingerprint != fingerprint:
                raise ExecutionOutcomeUncertain(
                    "Request fingerprint mismatch or missing fingerprint; "
                    "automatic replay is prohibited"
                )

            if record.state == "completed":
                if record.result_json is None:
                    raise ExecutionOutcomeUncertain("Completed claim has no recorded result")

                return CoordinationResult(
                    status=CoordinationStatus.REPLAYED,
                    data=dict(record.result_json),
                )

            if record.state == "in_progress":
                return CoordinationResult(status=CoordinationStatus.IN_PROGRESS)

            if record.state == "uncertain":
                return CoordinationResult(status=CoordinationStatus.UNCERTAIN)

            raise ExecutionOutcomeUncertain(f"Unknown execution state: {record.state}")

        # This coordinator owns the new claim.
        # Never automatically retry after the action is attempted.
        try:
            data = await action()

            if not isinstance(data, dict):
                raise TypeError("Tool execution must return a dictionary")

            completed = await self.claims.complete(tenant_id, key, owner, data)

            if not completed:
                raise ExecutionOutcomeUncertain(
                    "Execution completed, but claim completion was not confirmed"
                )

            return CoordinationResult(
                status=CoordinationStatus.EXECUTED,
                data=dict(data),
            )

        except asyncio.CancelledError:
            # The external action may already have taken effect.
            # Keep the uncertainty transition alive if this task
            # receives another cancellation.
            transition_task = asyncio.create_task(self.claims.mark_uncertain(tenant_id, key, owner))

            loop = asyncio.get_running_loop()
            deadline = loop.time() + 5.0

            try:
                while True:
                    remaining = deadline - loop.time()

                    if remaining <= 0:
                        logger.error(
                            "Uncertain state not confirmed: "
                            "persistence deadline exceeded; "
                            "manual reconciliation required"
                        )
                        break

                    try:
                        recorded = await asyncio.wait_for(
                            asyncio.shield(transition_task),
                            timeout=remaining,
                        )
                    except asyncio.CancelledError:
                        # Preserve the original cancellation but
                        # continue waiting for the persistence task.
                        continue
                    except TimeoutError:
                        logger.error(
                            "Uncertain state not confirmed: "
                            "persistence timed out; "
                            "manual reconciliation required"
                        )
                        break
                    except Exception:
                        logger.exception(
                            "Uncertain state persistence failed; manual reconciliation required"
                        )
                        break

                    if not recorded:
                        logger.error(
                            "Uncertain state not confirmed: "
                            "repository rejected the transition; "
                            "manual reconciliation required"
                        )

                    break
            finally:
                # No automatic retry or ownership transfer.
                # The persistence task may still run after a
                # timeout. Reconciliation must check the ledger.
                if transition_task.done():
                    try:
                        transition_task.result()
                    except asyncio.CancelledError:
                        logger.error("Uncertain state persistence task was cancelled")
                    except Exception:  # noqa: S110 -- The same exception was logged while awaiting this task above.
                        # Already handled while awaiting above.
                        pass

            raise

        except Exception as exc:
            # An external effect might have occurred already.
            # Make a best-effort transition to UNCERTAIN.
            try:
                recorded = await self.claims.mark_uncertain(tenant_id, key, owner)
            except Exception:
                recorded = False

            if not recorded:
                raise ExecutionOutcomeUncertain(
                    "Execution outcome unknown; could not confirm "
                    "the uncertain state. Reconciliation required."
                ) from exc

            raise ExecutionOutcomeUncertain(
                "Execution outcome unknown; claim marked uncertain. Reconciliation required."
            ) from exc
