"""Subscribers cannot rewrite another subscriber's event or the publisher's input."""

import asyncio
import unittest
from unittest.mock import AsyncMock

from core.events.bus import DomainEvent, InMemoryEventBus


def fixture_event():
    return DomainEvent(
        event_type="fixture.created",
        tenant_id="tenant-a",
        payload={"details": {"labels": ["original"]}},
    )


class EventSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bus = InMemoryEventBus()

    async def test_publisher_edits_do_not_rewrite_recorded_event(self):
        event = fixture_event()
        await self.bus.publish(event)
        event.tenant_id = "tenant-b"
        event.payload["details"]["labels"].append("changed")
        [recorded] = self.bus.published
        self.assertEqual(recorded.tenant_id, "tenant-a")
        self.assertEqual(recorded.payload["details"]["labels"], ["original"])

    async def test_subscriber_edits_do_not_rewrite_publisher_input(self):
        async def mutate(event):
            event.event_type = "changed"
            event.tenant_id = "tenant-b"
            event.payload["details"]["labels"].append("changed")

        self.bus.subscribe("fixture.created", mutate)
        event = fixture_event()
        await self.bus.publish(event)
        self.assertEqual(event.event_type, "fixture.created")
        self.assertEqual(event.tenant_id, "tenant-a")
        self.assertEqual(event.payload["details"]["labels"], ["original"])

    async def test_subscriber_edits_do_not_reach_later_subscribers(self):
        async def mutate(event):
            event.tenant_id = "tenant-b"
            event.payload["details"]["labels"].append("changed")

        observer = AsyncMock()
        self.bus.subscribe("fixture.created", mutate)
        self.bus.subscribe("fixture.created", observer)
        await self.bus.publish(fixture_event())
        observed = observer.await_args.args[0]
        self.assertEqual(observed.tenant_id, "tenant-a")
        self.assertEqual(observed.payload["details"]["labels"], ["original"])

    async def test_wildcard_subscribers_receive_independent_snapshots(self):
        async def mutate(event):
            event.payload.clear()

        observer = AsyncMock()
        self.bus.subscribe("fixture.created", mutate)
        self.bus.subscribe("*", observer)
        await self.bus.publish(fixture_event())
        self.assertEqual(observer.await_args.args[0].payload, {"details": {"labels": ["original"]}})

    async def test_subscriber_edits_do_not_rewrite_recorded_event(self):
        async def mutate(event):
            event.event_type = "changed"
            event.payload.clear()

        self.bus.subscribe("fixture.created", mutate)
        await self.bus.publish(fixture_event())
        [recorded] = self.bus.published
        self.assertEqual(recorded.event_type, "fixture.created")
        self.assertEqual(recorded.payload, {"details": {"labels": ["original"]}})

    async def test_failed_subscriber_cannot_corrupt_later_delivery_or_log_identity(self):
        async def fail(event):
            event.event_type = "changed"
            event.payload.clear()
            raise RuntimeError("fixture subscriber failure")

        observer = AsyncMock()
        self.bus.subscribe("fixture.created", fail)
        self.bus.subscribe("*", observer)
        with self.assertLogs("core.events.bus", level="ERROR") as captured:
            await self.bus.publish(fixture_event())
        self.assertEqual(captured.records[0].event_type, "fixture.created")
        self.assertEqual(observer.await_args.args[0].payload, {"details": {"labels": ["original"]}})

    async def test_history_edits_during_delivery_do_not_change_later_delivery(self):
        async def mutate_history(event):
            self.bus.published[0].payload.clear()

        observer = AsyncMock()
        self.bus.subscribe("fixture.created", mutate_history)
        self.bus.subscribe("*", observer)
        await self.bus.publish(fixture_event())
        self.assertEqual(observer.await_args.args[0].payload, {"details": {"labels": ["original"]}})

    async def test_event_identity_and_timestamp_are_preserved_across_deliveries(self):
        first, second = AsyncMock(), AsyncMock()
        self.bus.subscribe("fixture.created", first)
        self.bus.subscribe("*", second)
        event = fixture_event()
        await self.bus.publish(event)
        for received in (
            first.await_args.args[0],
            second.await_args.args[0],
            self.bus.published[0],
        ):
            self.assertEqual(received.model_dump(), event.model_dump())
            self.assertIsNot(received, event)
        self.assertIsNot(first.await_args.args[0], second.await_args.args[0])

    async def test_cancellation_still_propagates_and_stops_delivery(self):
        cancelled = AsyncMock(side_effect=asyncio.CancelledError)
        observer = AsyncMock()
        self.bus.subscribe("fixture.created", cancelled)
        self.bus.subscribe("*", observer)
        with self.assertRaises(asyncio.CancelledError):
            await self.bus.publish(fixture_event())
        cancelled.assert_awaited_once()
        observer.assert_not_awaited()
