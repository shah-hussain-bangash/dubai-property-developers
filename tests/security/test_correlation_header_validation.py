"""Only complete, well-formed request IDs may reach response headers and context."""

import unittest
from unittest.mock import AsyncMock, patch

from starlette.requests import Request
from starlette.responses import Response

from apps.api.app.middleware.correlation import CorrelationIdMiddleware
from core.observability.context import get_correlation_id

GENERATED = "generated-fixture-id"


class CorrelationHeaderValidationTests(unittest.IsolatedAsyncioTestCase):
    async def check_headers(self, headers, expected):
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/fixture",
                "headers": [
                    (key.lower().encode(), value.encode("latin-1")) for key, value in headers
                ],
                "query_string": b"",
            }
        )
        middleware = CorrelationIdMiddleware(AsyncMock())
        call_next = AsyncMock(return_value=Response())
        with (
            patch("apps.api.app.middleware.correlation.new_correlation_id", return_value=GENERATED),
            patch("apps.api.app.middleware.correlation.logger.info") as logged,
        ):
            response = await middleware.dispatch(request, call_next)
        self.assertEqual(response.headers["X-Correlation-ID"], expected)
        self.assertEqual(request.state.correlation_id, expected)
        self.assertEqual(get_correlation_id(), expected)
        self.assertNotIn("\n", response.headers["X-Correlation-ID"])
        self.assertNotIn("\r", response.headers["X-Correlation-ID"])
        logged.assert_called_once()
        call_next.assert_awaited_once_with(request)

    async def test_final_newlines_and_other_invalid_characters_are_replaced(self):
        for value in (
            "fixture-safe-id\n",
            "fixture-safe-id\r\n",
            "fixture-safe-id\r",
            "fixture\nsafe-id",
            "fixture-safe-id ",
            " fixture-safe-id",
            "fixture-safe-id\t",
            "fixture-safe-id\x00",
            "fixture-safe-idé",
        ):
            with self.subTest(value=value):
                await self.check_headers([("X-Correlation-ID", value)], GENERATED)

    async def test_valid_ascii_ids_at_both_length_limits_are_preserved(self):
        for value in ("a" * 8, "A0_b-C12", "x" * 64):
            with self.subTest(value=value):
                await self.check_headers([("X-Correlation-ID", value)], value)

    async def test_missing_empty_and_out_of_range_ids_are_replaced(self):
        await self.check_headers([], GENERATED)
        for value in ("", "x" * 7, "x" * 65, "x" * 1000):
            with self.subTest(length=len(value)):
                await self.check_headers([("X-Correlation-ID", value)], GENERATED)

    async def test_request_id_fallback_uses_the_same_complete_validation(self):
        for value, expected in (
            ("fallback-request-id", "fallback-request-id"),
            ("fallback-request-id\n", GENERATED),
        ):
            with self.subTest(value=value):
                await self.check_headers([("X-Request-ID", value)], expected)

    async def test_primary_header_precedence_is_preserved(self):
        await self.check_headers(
            [("X-Correlation-ID", "primary-request-id"), ("X-Request-ID", "fallback-request-id")],
            "primary-request-id",
        )
        await self.check_headers(
            [("X-Correlation-ID", "primary-request-id\n"), ("X-Request-ID", "fallback-request-id")],
            GENERATED,
        )
