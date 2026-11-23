"""Integration credentials are sent only to the configured service origin."""

import secrets
import unittest
from unittest.mock import Mock

import httpx

from core.resilience.retry import RetryPolicy
from integrations.base import HttpIntegrationClient, IntegrationRequestRejected


class IntegrationOriginBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, handler):
        auth = Mock()
        auth.headers.return_value = {"Authorization": "Bearer " + secrets.token_hex(16)}
        client = HttpIntegrationClient(
            integration="fixture",
            base_url="https://service.example.test/api/v1",
            auth=auth,
            retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0, jitter=False),
            transport=httpx.MockTransport(handler),
        )
        self.addAsyncCleanup(client.aclose)
        return client, auth

    async def test_other_origins_are_rejected_before_authentication_or_network_access(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"fixture": "result"})

        client, auth = self.make_client(handler)
        for path in (
            "https://other.example.test/items",
            "https://service.example.test.attacker.example/items",
            "http://service.example.test/items",
            "https://service.example.test:8443/items",
            "ftp://service.example.test/items",
        ):
            with self.subTest(path=path):
                with self.assertRaisesRegex(IntegrationRequestRejected, "configured origin"):
                    await client.request("GET", path)
                auth.headers.assert_not_called()
                self.assertEqual(calls, [])

    async def test_same_origin_url_keeps_authentication_and_normalizes_default_port(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"fixture": "result"})

        client, auth = self.make_client(handler)

        result = await client.request("GET", "https://SERVICE.EXAMPLE.TEST:443/items")

        self.assertEqual(result, {"fixture": "result"})
        self.assertEqual(str(calls[0].url), "https://service.example.test/items")
        self.assertEqual(
            calls[0].headers["Authorization"], auth.headers.return_value["Authorization"]
        )
        auth.headers.assert_called_once_with()

    async def test_relative_path_preserves_base_prefix_query_and_idempotency_header(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"fixture": "result"})

        client, auth = self.make_client(handler)

        await client.request(
            "POST", "/items", params={"fixture": "query"}, idempotency_key="fixture-key"
        )

        self.assertEqual(
            str(calls[0].url), "https://service.example.test/api/v1/items?fixture=query"
        )
        self.assertEqual(calls[0].headers["Idempotency-Key"], "fixture-key")
        self.assertEqual(
            calls[0].headers["Authorization"], auth.headers.return_value["Authorization"]
        )

    async def test_allowed_request_retries_at_the_same_origin(self):
        calls = []

        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(503)
            return httpx.Response(200, json={"fixture": "result"})

        client, auth = self.make_client(handler)

        result = await client.request("GET", "/items")

        self.assertEqual(result, {"fixture": "result"})
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].url, calls[1].url)
        for request in calls:
            self.assertEqual(request.url.host, "service.example.test")
            self.assertEqual(
                request.headers["Authorization"], auth.headers.return_value["Authorization"]
            )
