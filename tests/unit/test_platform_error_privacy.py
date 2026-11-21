"""Server-side platform diagnostics must not become public response content."""

import json
import secrets
import unittest
from unittest.mock import patch

from starlette.requests import Request

from apps.api.app.exception_handlers.handlers import platform_error_handler
from core.exceptions.errors import (
    AgentTimeoutError,
    ApprovalRequiredError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ConflictError,
    DomainValidationError,
    IntegrationError,
    IntegrationNotConfiguredError,
    NotFoundError,
    PlatformError,
    RateLimitExceededError,
)
from core.observability.context import set_correlation_id


class PlatformErrorPrivacyTests(unittest.IsolatedAsyncioTestCase):
    def request(self):
        return Request({"type": "http", "method": "GET", "path": "/fixture", "headers": []})

    async def test_server_errors_keep_status_code_and_correlation_without_private_content(self):
        private = "fixture-private-" + secrets.token_hex(16)
        for error_type in (
            PlatformError,
            ConfigurationError,
            IntegrationError,
            IntegrationNotConfiguredError,
            AgentTimeoutError,
        ):
            with self.subTest(error_type=error_type):
                details = {"internal": private, "nested": {"diagnostic": private}}
                error = error_type(private, details=details)
                set_correlation_id("fixture-correlation-123")
                response = await platform_error_handler(self.request(), error)
                body = json.loads(response.body)["error"]
                self.assertEqual(response.status_code, error.status_code)
                self.assertEqual(
                    body,
                    {
                        "code": error.code,
                        "message": "An unexpected error occurred",
                        "details": {},
                        "correlation_id": "fixture-correlation-123",
                    },
                )
                self.assertNotIn(private, response.body.decode())
                self.assertEqual(error.message, private)
                self.assertEqual(error.details, details)

    async def test_client_errors_retain_actionable_message_and_details(self):
        for error_type in (
            AuthenticationError,
            AuthorizationError,
            DomainValidationError,
            NotFoundError,
            ConflictError,
            RateLimitExceededError,
        ):
            with self.subTest(error_type=error_type):
                error = error_type("Fixture action required", details={"field": "fixture"})
                response = await platform_error_handler(self.request(), error)
                body = json.loads(response.body)["error"]
                self.assertEqual(response.status_code, error.status_code)
                self.assertEqual(body["code"], error.code)
                self.assertEqual(body["message"], error.message)
                self.assertEqual(body["details"], error.details)

    async def test_approval_response_retains_approval_identifier(self):
        error = ApprovalRequiredError("Fixture approval", approval_id="fixture-approval-id")
        response = await platform_error_handler(self.request(), error)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            json.loads(response.body)["error"]["details"],
            {"approval_id": "fixture-approval-id"},
        )

    async def test_non_serializable_server_details_cannot_break_error_response(self):
        error = IntegrationError("Fixture private failure", details={"opaque": object()})
        response = await platform_error_handler(self.request(), error)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(json.loads(response.body)["error"]["details"], {})

    async def test_server_error_logging_retains_only_machine_readable_code(self):
        error = IntegrationError("Fixture private message", details={"private": "fixture-value"})
        with patch("apps.api.app.exception_handlers.handlers.logger.warning") as logged:
            await platform_error_handler(self.request(), error)
        logged.assert_called_once_with("platform error", extra={"error_code": "integration_error"})
