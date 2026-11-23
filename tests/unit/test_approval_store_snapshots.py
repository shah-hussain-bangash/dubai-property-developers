"""Approval records cannot be changed through caller-owned or returned objects."""

import unittest
from datetime import UTC, datetime, timedelta

from core.exceptions.errors import ConflictError, NotFoundError
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


class ApprovalSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = InMemoryApprovalStore()

    async def assert_pending_original(self, approval_id):
        saved = await self.store.get(approval_id)
        self.assertEqual(saved.status, ApprovalStatus.PENDING)
        self.assertEqual(saved.payload["details"]["labels"], ["original"])
        self.assertEqual(saved.tenant_id, "tenant-a")

    def tamper(self, request):
        request.status = ApprovalStatus.APPROVED
        request.tenant_id = "tenant-b"
        request.payload["details"]["labels"].append("changed")

    async def test_create_detaches_the_input_record(self):
        request = fixture_request()
        await self.store.create(request)
        self.tamper(request)
        await self.assert_pending_original(request.approval_id)

    async def test_create_returns_an_independent_record(self):
        created = await self.store.create(fixture_request())
        self.tamper(created)
        await self.assert_pending_original(created.approval_id)

    async def test_get_returns_an_independent_record(self):
        created = await self.store.create(fixture_request())
        retrieved = await self.store.get(created.approval_id)
        self.tamper(retrieved)
        await self.assert_pending_original(created.approval_id)

    async def test_idempotency_lookup_returns_an_independent_record(self):
        created = await self.store.create(fixture_request())
        found = await self.store.find_by_idempotency_key("fixture-key")
        self.tamper(found)
        await self.assert_pending_original(created.approval_id)
        self.assertIsNone(await self.store.find_by_idempotency_key("missing"))

    async def test_pending_list_returns_independent_records(self):
        created = await self.store.create(fixture_request())
        [pending] = await self.store.list_pending("tenant-a")
        self.tamper(pending)
        await self.assert_pending_original(created.approval_id)
        self.assertEqual(await self.store.list_pending("tenant-b"), [])

    async def test_decision_result_cannot_undo_or_rewrite_saved_decision(self):
        created = await self.store.create(fixture_request())
        decided = await self.store.decide(
            created.approval_id, approved=True, decided_by="manager", note="Reviewed"
        )
        decided.status = ApprovalStatus.PENDING
        decided.decided_by = "changed"
        decided.payload["details"]["labels"].append("changed")
        saved = await self.store.get(created.approval_id)
        self.assertEqual(saved.status, ApprovalStatus.APPROVED)
        self.assertEqual(saved.decided_by, "manager")
        self.assertEqual(saved.decision_note, "Reviewed")
        self.assertIsNotNone(saved.decided_at)
        self.assertEqual(saved.payload["details"]["labels"], ["original"])
        with self.assertRaises(ConflictError):
            await self.store.decide(created.approval_id, approved=False, decided_by="other")

    async def test_explicit_approval_and_rejection_are_persisted(self):
        for approved in (True, False):
            with self.subTest(approved=approved):
                created = await self.store.create(fixture_request())
                await self.store.decide(
                    created.approval_id, approved=approved, decided_by="manager"
                )
                saved = await self.store.get(created.approval_id)
                expected = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
                self.assertEqual(saved.status, expected)
                pending_ids = [
                    item.approval_id for item in await self.store.list_pending("tenant-a")
                ]
                self.assertNotIn(created.approval_id, pending_ids)

    async def test_expiration_is_persisted_before_the_conflict_is_raised(self):
        created = await self.store.create(
            fixture_request(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        with self.assertRaises(ConflictError):
            await self.store.decide(created.approval_id, approved=True, decided_by="manager")
        self.assertEqual((await self.store.get(created.approval_id)).status, ApprovalStatus.EXPIRED)
        self.assertEqual(await self.store.list_pending("tenant-a"), [])

    async def test_missing_records_still_raise_not_found(self):
        with self.assertRaises(NotFoundError):
            await self.store.get("missing")
        with self.assertRaises(NotFoundError):
            await self.store.decide("missing", approved=True, decided_by="manager")
