"""Experimental execution ownership primitives.

This module is an isolated in-memory prototype.
It is NOT a durable cross-process execution coordinator.

Do not wire it into production tools or workers.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ExecutionState(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class ExecutionRecord:
    key: str
    state: ExecutionState
    owner_token: str
    result: dict[str, Any] | None = None


class InMemoryExecutionClaimStore:
    """Atomic claim transitions within one Python event loop."""

    def __init__(self) -> None:
        self._records: dict[str, ExecutionRecord] = {}
        self._lock = asyncio.Lock()

    async def claim(self, key: str) -> ExecutionRecord | None:
        """Return a new claim, or None if the key is already claimed."""

        async with self._lock:
            if key in self._records:
                return None

            record = ExecutionRecord(
                key=key,
                state=ExecutionState.IN_PROGRESS,
                owner_token=uuid.uuid4().hex,
            )

            self._records[key] = record
            return record

    async def get(self, key: str) -> ExecutionRecord | None:
        async with self._lock:
            return self._records.get(key)

    async def complete(
        self,
        key: str,
        owner_token: str,
        result: dict[str, Any],
    ) -> ExecutionRecord:
        async with self._lock:
            current = self._require_owner(key, owner_token)

            if current.state != ExecutionState.IN_PROGRESS:
                raise ValueError(
                    "Only an in-progress execution can complete"
                )

            completed = ExecutionRecord(
                key=key,
                state=ExecutionState.COMPLETED,
                owner_token=owner_token,
                result=dict(result),
            )

            self._records[key] = completed
            return completed

    async def mark_uncertain(
        self,
        key: str,
        owner_token: str,
    ) -> ExecutionRecord:
        async with self._lock:
            current = self._require_owner(key, owner_token)

            if current.state != ExecutionState.IN_PROGRESS:
                raise ValueError(
                    "Only an in-progress execution can become uncertain"
                )

            uncertain = ExecutionRecord(
                key=key,
                state=ExecutionState.UNCERTAIN,
                owner_token=owner_token,
            )

            self._records[key] = uncertain
            return uncertain

    def _require_owner(
        self,
        key: str,
        owner_token: str,
    ) -> ExecutionRecord:
        current = self._records.get(key)

        if current is None:
            raise KeyError(f"Execution claim not found: {key}")

        if current.owner_token != owner_token:
            raise PermissionError(
                "Execution claim belongs to another owner"
            )

        return current
