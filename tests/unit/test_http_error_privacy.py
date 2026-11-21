"""HTTP server errors must not expose exception detail in public responses."""

import json
import secrets
import unittest

from fastapi import HTTPException
from starlette.requests import Request

from apps.api.app.exception_handlers.handlers import http_error_handler
from core.observability.context import set_correlation_id


class HttpErrorPrivacyTests(unittest.IsolatedAsyncioTestCase):
    def request(self):
        return Request({"type": "http", "method": "GET", "path": "/fixture", "headers": []})

    async def test_server_error_details_are_private_without_changing_status_or_code(self):
        private = "fixture-private-" + secrets.token_hex(16)
        for status in (500, 502, 503, 504):
            with self.subTest(status=status):
                detail = {"internal": private, "nested": {"diagnostic": private}}
                error = HTTPException(status_code=status, detail=detail)
                set_correlation_id("fixture-correlation-123")
                response = await http_error_handler(self.request(), error)
                self.assertEqual(response.status_code, status)
                self.assertEqual(
                    json.loads(response.body)["error"],
                    {
                        "code": f"http_{status}",
                        "message": "An unexpected error occurred",
                        "details": {},
                        "correlation_id": "fixture-correlation-123",
                    },
                )
                self.assertNotIn(private, response.body.decode())
                self.assertEqual(error.detail, detail)

    async def test_client_error_messages_remain_actionable(self):
        for status in (400, 401, 403, 404, 409, 422, 429):
            with self.subTest(status=status):
                error = HTTPException(status_code=status, detail="Fixture action required")
                response = await http_error_handler(self.request(), error)
                body = json.loads(response.body)["error"]
                self.assertEqual(response.status_code, status)
                self.assertEqual(body["code"], f"http_{status}")
                self.assertEqual(body["message"], "Fixture action required")

    async def test_retry_and_authentication_headers_are_preserved(self):
        for status, headers in (
            (503, {"Retry-After": "12"}),
            (401, {"WWW-Authenticate": "Bearer"}),
            (429, {"Retry-After": "7"}),
        ):
            with self.subTest(status=status):
                error = HTTPException(status_code=status, detail="Fixture detail", headers=headers)
                response = await http_error_handler(self.request(), error)
                for name, value in headers.items():
                    self.assertEqual(response.headers[name], value)

    async def test_server_detail_is_not_even_formatted(self):
        class InternalDiagnostic:
            def __str__(self):
                raise AssertionError("Internal diagnostics must not be formatted for clients")

        error = HTTPException(status_code=502, detail=InternalDiagnostic())
        response = await http_error_handler(self.request(), error)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            json.loads(response.body)["error"]["message"], "An unexpected error occurred"
        )
