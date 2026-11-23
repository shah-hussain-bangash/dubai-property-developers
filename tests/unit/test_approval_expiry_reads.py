"""Expired approvals leave the pending queue and retries find the newest request."""

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from core.exceptions.errors import ConflictError
from core.policies.approvals import ApprovalRequest, ApprovalStatus, InMemoryApprovalStore

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def fixture_request(**updates):
    values = {
        "tenant_id": "tenant-a",
        "tool_name": "fixture.send",
        "action_category": "outbound_message",
        "requested_by": "fixture-agent",
        "reason": "Fictional approval",
        "idempotency_key": "fixture-key",
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=1),
    }
    values.update(updates)
    return ApprovalRequest(**values)


class ApprovalExpiryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = InMemoryApprovalStore()
        self.clock_patch = patch("core.policies.approvals.datetime")
        self.clock = self.clock_patch.start()
        self.clock.now.return_value = NOW
        self.addCleanup(self.clock_patch.stop)

    async def test_get_expires_an_overdue_pending_request(self):
        created = await self.store.create(fixture_request())
        self.clock.now.return_value = NOW + timedelta(hours=2)
        self.assertEqual((await self.store.get(created.approval_id)).status, ApprovalStatus.EXPIRED)
        with self.assertRaises(ConflictError):
            await self.store.decide(created.approval_id, approved=True, decided_by="manager")

    async def test_lookup_expires_an_overdue_pending_request(self):
        created = await self.store.create(fixture_request())
        self.clock.now.return_value = NOW + timedelta(hours=2)
        found = await self.store.find_by_idempotency_key("fixture-key")
        self.assertEqual(found.status, ApprovalStatus.EXPIRED)
        self.assertEqual((await self.store.get(created.approval_id)).status, ApprovalStatus.EXPIRED)

    async def test_pending_queue_excludes_overdue_requests(self):
        await self.store.create(fixture_request())
        fresh = await self.store.create(fixture_request(expires_at=NOW + timedelta(hours=3)))
        self.clock.now.return_value = NOW + timedelta(hours=2)
        pending = await self.store.list_pending("tenant-a")
        self.assertEqual([request.approval_id for request in pending], [fresh.approval_id])

    async def test_request_expires_at_the_exact_deadline(self):
        created = await self.store.create(fixture_request())
        self.clock.now.return_value = created.expires_at
        self.assertEqual((await self.store.get(created.approval_id)).status, ApprovalStatus.EXPIRED)

    async def test_decided_requests_are_preserved_after_the_deadline(self):
        for approved in (True, False):
            with self.subTest(approved=approved):
                self.clock.now.return_value = NOW
                created = await self.store.create(fixture_request())
                await self.store.decide(
                    created.approval_id, approved=approved, decided_by="manager"
                )
                self.clock.now.return_value = NOW + timedelta(hours=2)
                saved = await self.store.get(created.approval_id)
                expected = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
                self.assertEqual(saved.status, expected)
                self.assertEqual(saved.decided_by, "manager")

    async def test_creating_an_overdue_request_returns_its_expired_state(self):
        created = await self.store.create(fixture_request(expires_at=NOW - timedelta(seconds=1)))
        self.assertEqual(created.status, ApprovalStatus.EXPIRED)
        self.assertEqual(await self.store.list_pending("tenant-a"), [])

    async def test_latest_request_is_returned_after_expired_predecessor(self):
        old = await self.store.create(fixture_request())
        self.clock.now.return_value = NOW + timedelta(hours=2)
        fresh = await self.store.create(fixture_request(expires_at=NOW + timedelta(hours=3)))
        found = await self.store.find_by_idempotency_key("fixture-key")
        self.assertEqual(found.approval_id, fresh.approval_id)
        self.assertNotEqual(found.approval_id, old.approval_id)
        self.assertEqual(found.status, ApprovalStatus.PENDING)

    async def test_latest_request_is_returned_after_rejected_predecessor(self):
        old = await self.store.create(fixture_request())
        await self.store.decide(old.approval_id, approved=False, decided_by="manager")
        fresh = await self.store.create(fixture_request())
        found = await self.store.find_by_idempotency_key("fixture-key")
        self.assertEqual(found.approval_id, fresh.approval_id)
        self.assertEqual(found.status, ApprovalStatus.PENDING)
