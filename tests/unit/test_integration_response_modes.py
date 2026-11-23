"""Slack's plain-text acknowledgements work without weakening JSON adapters."""

import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from pydantic import SecretStr

from core.resilience.retry import RetryPolicy
from integrations.base import HttpIntegrationClient, IntegrationRequestRejected, NoAuth
from integrations.slack.client import SlackConfig, WebhookSlackNotifier


class SlackAcknowledgementTests(unittest.IsolatedAsyncioTestCase):
    def make_notifier(self, handler):
        notifier = WebhookSlackNotifier(
            SlackConfig(
                webhook_url=SecretStr("https://hooks.example.test/services/demo"),
                max_attempts=3,
            ),
            transport=httpx.MockTransport(handler),
        )
        self.addAsyncCleanup(notifier._http.aclose)
        return notifier

    async def test_plain_text_success_is_accepted_once_with_original_payload(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, text="ok")

        notifier = self.make_notifier(handler)
        self.assertIsNone(await notifier.notify("fixture alert", idempotency_key="fixture"))
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].method, "POST")
        self.assertEqual(requests[0].url.path, "/services/demo")
        self.assertEqual(requests[0].headers["Accept"], "text/plain")
        self.assertEqual(json.loads(requests[0].content), {"text": "fixture alert"})

    async def test_rejected_webhook_is_not_retried(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(403, text="action_prohibited")

        notifier = self.make_notifier(handler)
        with self.assertRaises(IntegrationRequestRejected) as rejected:
            await notifier.notify("fixture", idempotency_key="fixture")
        self.assertEqual(len(calls), 1)
        self.assertEqual(rejected.exception.details["status"], 403)

    async def test_transient_error_recovers_to_plain_text_acknowledgement(self):
        responses = [httpx.Response(503), httpx.Response(200, text="ok")]
        calls = []

        def handler(request):
            calls.append(request)
            return responses.pop(0)

        notifier = self.make_notifier(handler)
        with patch("core.resilience.retry.asyncio.sleep", new_callable=AsyncMock) as sleep:
            await notifier.notify("fixture", idempotency_key="fixture")
        self.assertEqual(len(calls), 2)
        sleep.assert_awaited_once()


class IntegrationResponseModeTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, handler):
        client = HttpIntegrationClient(
            integration="fixture",
            base_url="https://integration.example.test",
            auth=NoAuth(),
            retry_policy=RetryPolicy(max_attempts=2),
            transport=httpx.MockTransport(handler),
        )
        self.addAsyncCleanup(client.aclose)
        return client

    async def test_json_remains_the_default(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"id": "fixture"})

        client = self.make_client(handler)
        self.assertEqual(await client.request("GET", "/record"), {"id": "fixture"})
        self.assertEqual(requests[0].headers["Accept"], "application/json")

    async def test_malformed_json_is_not_silently_accepted_or_retried(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, text="not json")

        client = self.make_client(handler)
        with self.assertRaises(json.JSONDecodeError):
            await client.request("GET", "/record")
        self.assertEqual(len(requests), 1)

    async def test_text_mode_preserves_response_text(self):
        client = self.make_client(lambda request: httpx.Response(200, text="acknowledged\n"))
        self.assertEqual(await client.request("POST", "/hook", expect_json=False), "acknowledged\n")

    async def test_empty_responses_remain_none_in_both_modes(self):
        client = self.make_client(lambda request: httpx.Response(204))
        for expect_json in (True, False):
            with self.subTest(expect_json=expect_json):
                self.assertIsNone(await client.request("POST", "/hook", expect_json=expect_json))

    async def test_transport_errors_still_retry_in_text_mode(self):
        requests = []

        def handler(request):
            requests.append(request)
            if len(requests) == 1:
                raise httpx.ConnectError("fixture", request=request)
            return httpx.Response(200, text="ok")

        client = self.make_client(handler)
        with patch("core.resilience.retry.asyncio.sleep", new_callable=AsyncMock) as sleep:
            self.assertEqual(await client.request("POST", "/hook", expect_json=False), "ok")
        self.assertEqual(len(requests), 2)
        sleep.assert_awaited_once()
