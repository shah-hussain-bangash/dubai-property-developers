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

from core.observability.context import get_correlation_id

EXEMPT_PATHS = frozenset({"/health", "/ready"})


class RateLimiter(Protocol):
    async def hit(self, key: str) -> bool:
        """Record a request; return False when the limit is exceeded."""
        ...


_MAX_WINDOW_SECONDS = 2**31 - 1


def _validate_rate_limit_parameters(limit: int, window_seconds: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    if (
        isinstance(window_seconds, bool)
        or not isinstance(window_seconds, int)
        or not 1 <= window_seconds <= _MAX_WINDOW_SECONDS
    ):
        raise ValueError(f"window_seconds must be an integer between 1 and {_MAX_WINDOW_SECONDS}")


class InMemoryFixedWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        _validate_rate_limit_parameters(limit, window_seconds)
        self.limit = limit
        self.window = window_seconds
        self._counts: dict[tuple[str, int], int] = {}
        self._last_cleanup_bucket: int | None = None

    async def hit(self, key: str) -> bool:
        bucket = int(time.time() // self.window)
        if bucket != self._last_cleanup_bucket:
            self._counts = {k: v for k, v in self._counts.items() if k[1] >= bucket}
            self._last_cleanup_bucket = bucket
        count = self._counts.get((key, bucket), 0) + 1
        self._counts[(key, bucket)] = count
        return count <= self.limit


_REDIS_HIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 or redis.call('TTL', KEYS[1]) == -1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


class RedisFixedWindowRateLimiter:
    def __init__(self, client: Any, limit: int, window_seconds: int = 60) -> None:
        _validate_rate_limit_parameters(limit, window_seconds)
        self._client = client
        self.limit = limit
        self.window = window_seconds

    async def hit(self, key: str) -> bool:
        redis_key = f"ratelimit:{key}:{int(time.time() // self.window)}"
        count = await self._client.eval(_REDIS_HIT_SCRIPT, 1, redis_key, self.window)
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
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests",
                        "details": {},
                        "correlation_id": get_correlation_id(),
                    }
                },
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
