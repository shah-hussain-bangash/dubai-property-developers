"""Idempotency keys for external side effects.

Every action that touches a live system (send message, write CRM, book meeting)
is executed through ``IdempotencyStore`` so retries never duplicate the effect.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Protocol


def make_idempotency_key(action: str, payload: dict[str, Any], scope: str = "") -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(f"{scope}|{action}|{canonical}".encode()).hexdigest()
    return f"{action}:{digest[:40]}"


class IdempotencyStore(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...

    async def put(self, key: str, result: dict[str, Any], ttl_seconds: int) -> None: ...


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, result = item
        if expires_at < time.time():
            self._items.pop(key, None)
            return None
        return result

    async def put(self, key: str, result: dict[str, Any], ttl_seconds: int) -> None:
        self._items[key] = (time.time() + ttl_seconds, result)


class RedisIdempotencyStore:
    """Redis-backed store. ``client`` is a ``redis.asyncio.Redis`` instance."""

    def __init__(self, client: Any, prefix: str = "idem:") -> None:
        self._client = client
        self._prefix = prefix

    async def get(self, key: str) -> dict[str, Any] | None:
        raw = await self._client.get(self._prefix + key)
        return json.loads(raw) if raw else None

    async def put(self, key: str, result: dict[str, Any], ttl_seconds: int) -> None:
        await self._client.set(self._prefix + key, json.dumps(result, default=str), ex=ttl_seconds)
