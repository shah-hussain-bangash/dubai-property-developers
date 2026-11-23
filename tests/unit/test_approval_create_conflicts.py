"""Creating an approval never replaces an existing request or decision."""

import asyncio
import unittest
from datetime import UTC, datetime, timedelta

from core.exceptions.errors import ConflictError
from core.policies.approvals import ApprovalRequest, ApprovalStatus, InMemoryApprovalStore


def fixture_request(**updates):
    values = {
        "tenant_id": "tenant-a",
        "tool_name": "fixture.send",
        "action_category": "outbound_message",
        "requested_by": "fixture-agent",
        "reason": "Fictional approval",
        "payload": {"details": {"labels": ["original"]}},
        "idempotency_key": "fixture-key",
    }
    values.update(updates)
    return ApprovalRequest(**values)


class ApprovalCreateConflictTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = InMemoryApprovalStore()

    async def test_duplicate_id_cannot_replace_pending_payload_identity_or_status(self):
        original = await self.store.create(fixture_request())
        duplicate = fixture_request(
            approval_id=original.approval_id,
            tenant_id="tenant-b",
            tool_name="fixture.other",
            payload={"details": {"labels": ["replacement"]}},
            status=ApprovalStatus.APPROVED,
            idempotency_key="replacement-key",
        )
        with self.assertRaisesRegex(ConflictError, "already exists"):
            await self.store.create(duplicate)
        saved = await self.store.get(original.approval_id)
        self.assertEqual(saved.model_dump(), original.model_dump())
        found = await self.store.find_by_idempotency_key("fixture-key")
        self.assertEqual(found.approval_id, original.approval_id)
        self.assertIsNone(await self.store.find_by_idempotency_key("replacement-key"))

    async def test_duplicate_id_cannot_reset_decided_or_expired_records(self):
        for status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED):
            with self.subTest(status=status):
                if status == ApprovalStatus.EXPIRED:
                    request = fixture_request(expires_at=datetime.now(UTC) - timedelta(seconds=1))
                else:
                    request = fixture_request()
                original = await self.store.create(request)
                if status != ApprovalStatus.EXPIRED:
                    original = await self.store.decide(
                        original.approval_id,
                        approved=status == ApprovalStatus.APPROVED,
                        decided_by="manager",
                        note="Reviewed",
                    )
                with self.assertRaises(ConflictError):
                    await self.store.create(fixture_request(approval_id=original.approval_id))
                saved = await self.store.get(original.approval_id)
                self.assertEqual(saved.model_dump(), original.model_dump())

    async def test_identical_duplicate_is_reported_as_a_conflict(self):
        original = await self.store.create(fixture_request())
        with self.assertRaises(ConflictError):
            await self.store.create(original)
        self.assertEqual(len(await self.store.list_pending("tenant-a")), 1)

    async def test_distinct_ids_can_still_replace_a_stale_idempotency_request(self):
        old = await self.store.create(fixture_request())
        await self.store.decide(old.approval_id, approved=False, decided_by="manager")
        fresh = await self.store.create(fixture_request())
        self.assertNotEqual(old.approval_id, fresh.approval_id)
        found = await self.store.find_by_idempotency_key("fixture-key")
        self.assertEqual(found.approval_id, fresh.approval_id)

    async def test_concurrent_creation_has_one_winner_and_one_conflict(self):
        request = fixture_request()
        outcomes = await asyncio.gather(
            self.store.create(request),
            self.store.create(request.model_copy(deep=True)),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(item, ApprovalRequest) for item in outcomes), 1)
        self.assertEqual(sum(isinstance(item, ConflictError) for item in outcomes), 1)
        self.assertEqual(len(await self.store.list_pending("tenant-a")), 1)
