"""Rate limiting integration point (fixed window per client key).

The in-memory limiter is per-process (fine for local dev). Use the Redis limiter
when running multiple API replicas.
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

EXEMPT_PATHS = frozenset({"/health", "/ready"})


class RateLimiter(Protocol):
    async def hit(self, key: str) -> bool:
        """Record a request; return False when the limit is exceeded."""
        ...


class InMemoryFixedWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window = window_seconds
        self._counts: dict[tuple[str, int], int] = {}

    async def hit(self, key: str) -> bool:
        bucket = int(time.time() // self.window)
        self._counts = {k: v for k, v in self._counts.items() if k[1] >= bucket}
        count = self._counts.get((key, bucket), 0) + 1
        self._counts[(key, bucket)] = count
        return count <= self.limit


class RedisFixedWindowRateLimiter:
    def __init__(self, client: Any, limit: int, window_seconds: int = 60) -> None:
        self._client = client
        self.limit = limit
        self.window = window_seconds

    async def hit(self, key: str) -> bool:
        redis_key = f"ratelimit:{key}:{int(time.time() // self.window)}"
        count = await self._client.incr(redis_key)
        if count == 1:
            await self._client.expire(redis_key, self.window)
        return int(count) <= self.limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, limiter: RateLimiter) -> None:
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)
        # Behind a proxy, configure uvicorn --proxy-headers / trusted hosts so this is the real IP.
        key = request.client.host if request.client else "unknown"
        if not await self._limiter.hit(key):
            return JSONResponse(
                status_code=429,
                content={
                    "error": {"code": "rate_limited", "message": "Too many requests", "details": {}}
                },
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
