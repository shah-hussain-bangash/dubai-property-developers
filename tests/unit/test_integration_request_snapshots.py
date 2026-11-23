"""HTTP retries retain the original data and idempotency-key pairing."""

import asyncio
import json
import unittest

import httpx

from core.resilience.retry import RetryPolicy
from integrations.base import HttpIntegrationClient, NoAuth


class IntegrationRequestSnapshotTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, handler):
        client = HttpIntegrationClient(
            integration="fixture",
            base_url="https://service.example.test",
            auth=NoAuth(),
            retry_policy=RetryPolicy(
                max_attempts=2, base_delay_seconds=0, timeout_seconds=1, jitter=False
            ),
            transport=httpx.MockTransport(handler),
        )
        self.addAsyncCleanup(client.aclose)
        return client

    async def test_retry_keeps_nested_json_after_caller_mutation(self):
        started, release = asyncio.Event(), asyncio.Event()
        requests = []

        async def handler(request):
            requests.append(request)
            if len(requests) == 1:
                started.set()
                await release.wait()
                return httpx.Response(503)
            return httpx.Response(200, json={"fixture": "result"})

        client = self.make_client(handler)
        payload = {"items": [{"id": "fixture-original"}], "labels": ["original"]}
        task = asyncio.create_task(
            client.request("POST", "/items", json=payload, idempotency_key="fixture-key")
        )
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            payload["items"][0]["id"] = "fixture-changed"
            payload["labels"].append("changed")
        finally:
            release.set()
        await asyncio.wait_for(task, timeout=1)

        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].content, requests[1].content)
        self.assertEqual(
            json.loads(requests[1].content),
            {"items": [{"id": "fixture-original"}], "labels": ["original"]},
        )
        self.assertEqual(payload["items"][0]["id"], "fixture-changed")
        for request in requests:
            self.assertEqual(request.headers["Idempotency-Key"], "fixture-key")

    async def test_retry_keeps_query_values_after_caller_mutation(self):
        started, release = asyncio.Event(), asyncio.Event()
        requests = []

        async def handler(request):
            requests.append(request)
            if len(requests) == 1:
                started.set()
                await release.wait()
                return httpx.Response(503)
            return httpx.Response(200, json={"fixture": "result"})

        client = self.make_client(handler)
        params = {"label": ["fixture-original"], "page": 1}
        task = asyncio.create_task(client.request("GET", "/items", params=params))
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            params["label"].append("fixture-changed")
            params["page"] = 2
        finally:
            release.set()
        await asyncio.wait_for(task, timeout=1)

        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].url, requests[1].url)
        self.assertEqual(
            requests[1].url.params.multi_items(), [("label", "fixture-original"), ("page", "1")]
        )
        self.assertEqual(params["page"], 2)

    async def test_overlapping_calls_keep_independent_data_for_their_keys(self):
        started, release = asyncio.Event(), asyncio.Event()
        requests = []

        async def handler(request):
            requests.append(request)
            if len(requests) == 1:
                started.set()
                await release.wait()
                return httpx.Response(503)
            return httpx.Response(200, json={"fixture": "result"})

        client = self.make_client(handler)
        payload = {"fixture": {"value": "first"}}
        first = asyncio.create_task(
            client.request("POST", "/items", json=payload, idempotency_key="fixture-first")
        )
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            payload["fixture"]["value"] = "second"
            await client.request("POST", "/items", json=payload, idempotency_key="fixture-second")
        finally:
            release.set()
        await asyncio.wait_for(first, timeout=1)

        self.assertEqual(len(requests), 3)
        expected = {"fixture-first": "first", "fixture-second": "second"}
        for request in requests:
            key = request.headers["Idempotency-Key"]
            self.assertEqual(json.loads(request.content), {"fixture": {"value": expected[key]}})
