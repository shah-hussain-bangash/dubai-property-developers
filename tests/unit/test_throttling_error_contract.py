"""Throttling errors follow the documented correlation-ID response contract."""

import json
import unittest
from unittest.mock import AsyncMock

from starlette.requests import Request
from starlette.responses import Response

from apps.api.app.middleware.rate_limit import RateLimitMiddleware
from core.observability.context import set_correlation_id


class ThrottlingErrorContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_error_body_uses_current_request_correlation_context(self):
        for correlation in ("fixture-correlation-123", None):
            with self.subTest(correlation=correlation):
                limiter = AsyncMock()
                limiter.hit.return_value = False
                middleware = RateLimitMiddleware(AsyncMock(), limiter)
                request = Request(
                    {
                        "type": "http",
                        "method": "GET",
                        "path": "/fixture",
                        "headers": [],
                        "client": ("127.0.0.1", 12345),
                    }
                )
                call_next = AsyncMock(return_value=Response())
                set_correlation_id(correlation)
                response = await middleware.dispatch(request, call_next)
                self.assertEqual(response.status_code, 429)
                self.assertEqual(
                    json.loads(response.body)["error"],
                    {
                        "code": "rate_limited",
                        "message": "Too many requests",
                        "details": {},
                        "correlation_id": correlation,
                    },
                )
                self.assertEqual(response.headers["Retry-After"], "60")
                call_next.assert_not_awaited()
