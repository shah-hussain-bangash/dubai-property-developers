"""Idempotent results are snapshots rather than shared mutable objects."""

import asyncio
import unittest
from unittest.mock import patch

from core.resilience.idempotency import InMemoryIdempotencyStore


def result():
    return {"receipt": {"items": [{"id": "fixture-item"}], "labels": ["fixture"]}}


class IdempotencySnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_put_detaches_nested_input_before_caller_mutation(self):
        store = InMemoryIdempotencyStore()
        original = result()
        await store.put("fixture-key", original, 60)
        original["receipt"]["items"][0]["id"] = "changed"
        original["receipt"]["labels"].append("changed")
        original["extra"] = True
        self.assertEqual(await store.get("fixture-key"), result())

    async def test_get_detaches_nested_result_before_caller_mutation(self):
        store = InMemoryIdempotencyStore()
        await store.put("fixture-key", result(), 60)
        first = await store.get("fixture-key")
        first["receipt"]["items"].clear()
        first["receipt"]["labels"].append("changed")
        self.assertEqual(await store.get("fixture-key"), result())

    async def test_concurrent_reads_do_not_share_mutable_nested_data(self):
        store = InMemoryIdempotencyStore()
        await store.put("fixture-key", result(), 60)
        first, second = await asyncio.gather(store.get("fixture-key"), store.get("fixture-key"))
        first["receipt"]["items"][0]["id"] = "changed"
        self.assertEqual(second, result())
        self.assertEqual(await store.get("fixture-key"), result())

    async def test_overwrite_and_other_keys_remain_independent(self):
        store = InMemoryIdempotencyStore()
        await store.put("first", result(), 60)
        await store.put("second", result(), 60)
        old = await store.get("first")
        replacement = {"receipt": {"items": [{"id": "replacement"}]}}
        await store.put("first", replacement, 60)
        replacement["receipt"]["items"].clear()
        old["receipt"]["items"].clear()
        self.assertEqual(await store.get("first"), {"receipt": {"items": [{"id": "replacement"}]}})
        self.assertEqual(await store.get("second"), result())

    async def test_missing_and_expired_results_keep_existing_behavior(self):
        store = InMemoryIdempotencyStore()
        self.assertIsNone(await store.get("missing"))
        with patch("core.resilience.idempotency.time.time") as clock:
            clock.return_value = 1000.0
            await store.put("fixture-key", result(), 30)
            clock.return_value = 1029.999
            self.assertEqual(await store.get("fixture-key"), result())
            clock.return_value = 1030.001
            self.assertIsNone(await store.get("fixture-key"))
