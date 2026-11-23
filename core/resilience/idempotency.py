"""Idempotency keys for external side effects.

Successful side-effect results can be replayed instead of executing again.
Store-scoped locks serialize callers sharing one store instance in one event
loop. They do not provide distributed or external exactly-once guarantees.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from copy import deepcopy
from typing import Any, Protocol
from weakref import WeakValueDictionary


def make_idempotency_key(action: str, payload: dict[str, Any], scope: str = "") -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(f"{scope}|{action}|{canonical}".encode()).hexdigest()
    return f"{action}:{digest[:40]}"


class IdempotencyStore(Protocol):
    def execution_lock(self, key: str) -> asyncio.Lock:
        """Serialize local callers sharing this store instance and key."""
        ...

    async def get(self, key: str) -> dict[str, Any] | None:
        """Return a result snapshot that callers may mutate independently."""
        ...

    async def put(self, key: str, result: dict[str, Any], ttl_seconds: int) -> None:
        """Store a snapshot independent of later changes to the supplied result."""
        ...


class InMemoryIdempotencyStore:
    """Process-local result snapshots with TTLs measured by a monotonic clock."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}
        self._execution_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    def execution_lock(self, key: str) -> asyncio.Lock:
        # No await between lookup and insertion. Active holders and waiters keep
        # the lock alive; unused keys do not accumulate in the lock registry.
        return self._execution_locks.setdefault(key, asyncio.Lock())

    async def get(self, key: str) -> dict[str, Any] | None:
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, result = item
        if expires_at <= time.monotonic():
            self._items.pop(key, None)
            return None
        return deepcopy(result)

    async def put(self, key: str, result: dict[str, Any], ttl_seconds: int) -> None:
        self._items[key] = (time.monotonic() + ttl_seconds, deepcopy(result))


class RedisIdempotencyStore:
    """Redis-backed store. ``client`` is a ``redis.asyncio.Redis`` instance."""

    def __init__(self, client: Any, prefix: str = "idem:") -> None:
        self._client = client
        self._prefix = prefix
        self._execution_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    def execution_lock(self, key: str) -> asyncio.Lock:
        # This is deliberately local, not a Redis lease or a distributed fence.
        return self._execution_locks.setdefault(key, asyncio.Lock())

    async def get(self, key: str) -> dict[str, Any] | None:
        raw = await self._client.get(self._prefix + key)
        return json.loads(raw) if raw else None

    async def put(self, key: str, result: dict[str, Any], ttl_seconds: int) -> None:
        await self._client.set(self._prefix + key, json.dumps(result, default=str), ex=ttl_seconds)
