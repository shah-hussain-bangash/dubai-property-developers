from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from core.resilience.tool_execution_coordinator import (
    CoordinationStatus,
    ExecutionOutcomeUncertain,
    ToolExecutionCoordinator,
)


@dataclass
class FakeRecord:
    state: str
    owner_token: str
    tool_name: str
    request_fingerprint: str | None = None
    result_json: dict[str, Any] | None = None


class FakeClaimRepository:
    """In-memory test double with atomic claim operations."""

    def __init__(self) -> None:
        self.records: dict[tuple[str, str], FakeRecord] = {}
        self.lock = asyncio.Lock()
        self.fail_completion = False

    async def claim(
        self,
        tenant_id: str,
        key: str,
        tool_name: str,
        request_fingerprint: str | None = None,
    ) -> str | None:
        async with self.lock:
            identity = (tenant_id, key)

            if identity in self.records:
                return None

            token = uuid.uuid4().hex

            self.records[identity] = FakeRecord(
                state="in_progress",
                owner_token=token,
                tool_name=tool_name,
                request_fingerprint=request_fingerprint,
            )

            return token

    async def get(
        self,
        tenant_id: str,
        key: str,
    ) -> FakeRecord | None:
        async with self.lock:
            return self.records.get((tenant_id, key))

    async def complete(
        self,
        tenant_id: str,
        key: str,
        owner_token: str,
        result: dict[str, Any],
    ) -> bool:
        async with self.lock:
            record = self.records.get((tenant_id, key))

            if (
                record is None
                or record.owner_token != owner_token
                or record.state != "in_progress"
                or self.fail_completion
            ):
                return False

            record.state = "completed"
            record.result_json = dict(result)

            return True

    async def mark_uncertain(
        self,
        tenant_id: str,
        key: str,
        owner_token: str,
    ) -> bool:
        async with self.lock:
            record = self.records.get((tenant_id, key))

            if (
                record is None
                or record.owner_token != owner_token
                or record.state != "in_progress"
            ):
                return False

            record.state = "uncertain"
            return True


@pytest.mark.asyncio
async def test_first_execution_completes() -> None:
    claims = FakeClaimRepository()
    coordinator = ToolExecutionCoordinator(claims)
    calls = 0

    async def action() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"message_id": "message-1"}

    result = await coordinator.execute(
        "tenant-a",
        "key-1",
        "test.send",
        action,
     payload={})

    assert result.status == CoordinationStatus.EXECUTED
    assert result.data == {"message_id": "message-1"}
    assert calls == 1
    assert claims.records[("tenant-a", "key-1")].state == "completed"


@pytest.mark.asyncio
async def test_completed_execution_returns_replay() -> None:
    claims = FakeClaimRepository()
    coordinator = ToolExecutionCoordinator(claims)
    calls = 0

    async def action() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"message_id": "message-1"}

    first = await coordinator.execute(
        "tenant-a", "key-2", "test.send", action
    , payload={})

    second = await coordinator.execute(
        "tenant-a", "key-2", "test.send", action
    , payload={})

    assert first.status == CoordinationStatus.EXECUTED
    assert second.status == CoordinationStatus.REPLAYED
    assert second.data == first.data
    assert calls == 1


@pytest.mark.asyncio
async def test_two_coordinators_do_not_execute_twice() -> None:
    claims = FakeClaimRepository()

    coordinator_a = ToolExecutionCoordinator(claims)
    coordinator_b = ToolExecutionCoordinator(claims)

    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def action() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        started.set()

        await release.wait()

        return {"message_id": "message-1"}

    first_task = asyncio.create_task(
        coordinator_a.execute(
            "tenant-a", "key-3", "test.send", action
        , payload={})
    )

    try:
        await asyncio.wait_for(started.wait(), timeout=2)

        second = await coordinator_b.execute(
            "tenant-a", "key-3", "test.send", action
        , payload={})

        assert second.status == CoordinationStatus.IN_PROGRESS
        assert calls == 1

    finally:
        release.set()

    first = await asyncio.wait_for(first_task, timeout=2)

    assert first.status == CoordinationStatus.EXECUTED

    replay = await coordinator_b.execute(
        "tenant-a", "key-3", "test.send", action
    , payload={})

    assert replay.status == CoordinationStatus.REPLAYED
    assert calls == 1


@pytest.mark.asyncio
async def test_failed_external_action_becomes_uncertain() -> None:
    claims = FakeClaimRepository()
    coordinator = ToolExecutionCoordinator(claims)
    calls = 0

    async def action() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise RuntimeError("Simulated external API failure")

    with pytest.raises(ExecutionOutcomeUncertain):
        await coordinator.execute(
            "tenant-a", "key-4", "test.send", action
        , payload={})

    record = claims.records[("tenant-a", "key-4")]
    assert record.state == "uncertain"

    second = await coordinator.execute(
        "tenant-a", "key-4", "test.send", action
    , payload={})

    assert second.status == CoordinationStatus.UNCERTAIN
    assert calls == 1


@pytest.mark.asyncio
async def test_completion_failure_requires_reconciliation() -> None:
    claims = FakeClaimRepository()
    claims.fail_completion = True

    coordinator = ToolExecutionCoordinator(claims)
    calls = 0

    async def action() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"message_id": "message-5"}

    with pytest.raises(ExecutionOutcomeUncertain):
        await coordinator.execute(
            "tenant-a", "key-5", "test.send", action
        , payload={})

    assert calls == 1
    assert claims.records[("tenant-a", "key-5")].state == "uncertain"

    second = await coordinator.execute(
        "tenant-a", "key-5", "test.send", action
    , payload={})

    assert second.status == CoordinationStatus.UNCERTAIN
    assert calls == 1


@pytest.mark.asyncio
async def test_tenants_have_independent_claims() -> None:
    claims = FakeClaimRepository()
    coordinator = ToolExecutionCoordinator(claims)
    calls = 0

    async def action() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"message_id": f"message-{calls}"}

    first = await coordinator.execute(
        "tenant-a", "shared-key", "test.send", action
    , payload={})

    second = await coordinator.execute(
        "tenant-b", "shared-key", "test.send", action
    , payload={})

    assert first.status == CoordinationStatus.EXECUTED
    assert second.status == CoordinationStatus.EXECUTED
    assert calls == 2

@pytest.mark.asyncio
async def test_cancelled_execution_preserves_cancellation_and_blocks_retry() -> None:
    claims = FakeClaimRepository()
    coordinator = ToolExecutionCoordinator(claims)

    started = asyncio.Event()
    calls = 0

    async def action() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        started.set()
        await asyncio.Event().wait()
        return {"message_id": "unexpected"}

    task = asyncio.create_task(
        coordinator.execute(
            "tenant-a",
            "cancelled-key",
            "test.send",
            action,
         payload={})
    )

    await asyncio.wait_for(started.wait(), timeout=5)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    record = claims.records[("tenant-a", "cancelled-key")]
    assert record.state == "uncertain"

    replay = await coordinator.execute(
        "tenant-a",
        "cancelled-key",
        "test.send",
        action,
     payload={})

    assert replay.status == CoordinationStatus.UNCERTAIN
    assert calls == 1

@pytest.mark.asyncio
async def test_legacy_claim_without_fingerprint_cannot_replay() -> None:
    claims = FakeClaimRepository()

    claims.records[("tenant-a", "legacy-key")] = FakeRecord(
        state="completed",
        owner_token="legacy-owner",
        tool_name="crm.create_lead",
        request_fingerprint=None,
        result_json={"lead_id": "legacy-lead"},
    )

    coordinator = ToolExecutionCoordinator(claims)
    calls = 0

    async def action() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"lead_id": "new-lead"}

    with pytest.raises(
        ExecutionOutcomeUncertain,
        match="(?i)fingerprint",
    ):
        await coordinator.execute(
            "tenant-a",
            "legacy-key",
            "crm.create_lead",
            action,
            payload={"name": "Example Lead"},
        )

    assert calls == 0

@pytest.mark.asyncio
async def test_cancellation_waits_for_uncertain_state_recording() -> None:
    class SlowClaimRepository(FakeClaimRepository):
        def __init__(self) -> None:
            super().__init__()
            self.transition_started = asyncio.Event()
            self.allow_transition = asyncio.Event()

        async def mark_uncertain(
            self,
            tenant_id: str,
            key: str,
            owner_token: str,
        ) -> bool:
            self.transition_started.set()
            await self.allow_transition.wait()

            return await super().mark_uncertain(
                tenant_id,
                key,
                owner_token,
            )

    claims = SlowClaimRepository()
    coordinator = ToolExecutionCoordinator(claims)

    action_started = asyncio.Event()

    async def action() -> dict[str, Any]:
        action_started.set()
        await asyncio.Event().wait()
        return {"message_id": "unexpected"}

    task = asyncio.create_task(
        coordinator.execute(
            "tenant-a",
            "slow-cancellation",
            "test.send",
            action,
            payload={"message": "test"},
        )
    )

    try:
        await asyncio.wait_for(action_started.wait(), timeout=5)
        task.cancel()

        await asyncio.wait_for(
            claims.transition_started.wait(),
            timeout=5,
        )

        # Give the cancelled task an opportunity to finish
        # while the repository transition remains blocked.
        try:
            await asyncio.wait_for(
                asyncio.shield(task),
                timeout=0.1,
            )
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            pytest.fail(
                "Coordinator propagated cancellation before "
                "uncertain-state persistence completed"
            )
        else:
            pytest.fail(
                "Coordinator returned before uncertain-state "
                "persistence completed"
            )

        assert not task.done()

    finally:
        claims.allow_transition.set()

        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.CancelledError:
            pass

    record = claims.records[("tenant-a", "slow-cancellation")]

    assert record.state == "uncertain"

@pytest.mark.asyncio
async def test_repeated_cancellation_waits_for_uncertain_transition() -> None:
    class SlowClaims(FakeClaimRepository):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.finished = asyncio.Event()

        async def mark_uncertain(
            self, tenant_id: str, key: str, owner_token: str
        ) -> bool:
            self.started.set()
            await self.release.wait()
            result = await super().mark_uncertain(
                tenant_id, key, owner_token
            )
            self.finished.set()
            return result

    claims = SlowClaims()
    coordinator = ToolExecutionCoordinator(claims)
    action_started = asyncio.Event()

    async def action() -> dict[str, Any]:
        action_started.set()
        await asyncio.Event().wait()
        return {"message_id": "unexpected"}

    task = asyncio.create_task(
        coordinator.execute(
            "tenant-a",
            "repeated-cancellation",
            "test.send",
            action,
            payload={"message": "test"},
        )
    )

    try:
        await asyncio.wait_for(action_started.wait(), timeout=5)
        task.cancel()

        await asyncio.wait_for(claims.started.wait(), timeout=5)

        # Cancel again while uncertainty persistence is blocked.
        task.cancel()

        try:
            await asyncio.wait_for(
                asyncio.shield(task),
                timeout=0.2,
            )
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            pytest.fail(
                "Repeated cancellation allowed coordinator exit "
                "before uncertainty persistence finished"
            )
        else:
            pytest.fail("Coordinator exited prematurely")

        assert not task.done()
        assert not claims.finished.is_set()

    finally:
        claims.release.set()
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.CancelledError:
            pass

        await asyncio.wait_for(claims.finished.wait(), timeout=5)

    assert claims.records[
        ("tenant-a", "repeated-cancellation")
    ].state == "uncertain"


@pytest.mark.asyncio
async def test_cancellation_reports_unconfirmed_uncertain_transition(
    caplog,
) -> None:
    class RefusingClaims(FakeClaimRepository):
        async def mark_uncertain(
            self, tenant_id: str, key: str, owner_token: str
        ) -> bool:
            return False

    claims = RefusingClaims()
    coordinator = ToolExecutionCoordinator(claims)
    started = asyncio.Event()

    async def action() -> dict[str, Any]:
        started.set()
        await asyncio.Event().wait()
        return {"message_id": "unexpected"}

    task = asyncio.create_task(
        coordinator.execute(
            "tenant-a",
            "unconfirmed-cancellation",
            "test.send",
            action,
            payload={"message": "test"},
        )
    )

    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    assert claims.records[
        ("tenant-a", "unconfirmed-cancellation")
    ].state == "in_progress"

    assert any(
        "uncertain" in record.message.lower()
        and (
            "not confirmed" in record.message.lower()
            or "failed" in record.message.lower()
        )
        for record in caplog.records
        if record.levelno >= 40
    ), "An unconfirmed uncertainty update must be logged as an error"

@pytest.mark.asyncio
async def test_cancellation_logs_uncertain_database_exception(
    caplog,
) -> None:
    class FailingClaims(FakeClaimRepository):
        async def mark_uncertain(
            self, tenant_id: str, key: str, owner_token: str
        ) -> bool:
            raise ConnectionError("Simulated database disconnection")

    claims = FailingClaims()
    coordinator = ToolExecutionCoordinator(claims)
    started = asyncio.Event()

    async def action() -> dict[str, Any]:
        started.set()
        await asyncio.Event().wait()
        return {"message_id": "unexpected"}

    task = asyncio.create_task(
        coordinator.execute(
            "tenant-a",
            "database-error-test",
            "test.send",
            action,
            payload={"message": "test"},
        )
    )

    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    record = claims.records[
        ("tenant-a", "database-error-test")
    ]

    assert record.state == "in_progress"

    assert any(
        record.levelno >= 40
        and "uncertain" in record.message.lower()
        and "failed" in record.message.lower()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_cancellation_timeout_leaves_transition_pending(
    caplog,
) -> None:
    class DelayedClaims(FakeClaimRepository):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.finished = asyncio.Event()

        async def mark_uncertain(
            self, tenant_id: str, key: str, owner_token: str
        ) -> bool:
            self.started.set()
            await self.release.wait()

            result = await super().mark_uncertain(
                tenant_id, key, owner_token
            )
            self.finished.set()
            return result

    claims = DelayedClaims()
    coordinator = ToolExecutionCoordinator(claims)
    action_started = asyncio.Event()

    async def action() -> dict[str, Any]:
        action_started.set()
        await asyncio.Event().wait()
        return {"message_id": "unexpected"}

    task = asyncio.create_task(
        coordinator.execute(
            "tenant-a",
            "timeout-transition-test",
            "test.send",
            action,
            payload={"message": "test"},
        )
    )

    try:
        await asyncio.wait_for(
            action_started.wait(),
            timeout=5,
        )

        task.cancel()

        await asyncio.wait_for(
            claims.started.wait(),
            timeout=5,
        )

        # Current coordinator has a 5-second persistence deadline.
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=8)

        assert not claims.finished.is_set()

        assert claims.records[
            ("tenant-a", "timeout-transition-test")
        ].state == "in_progress"

        assert any(
            record.levelno >= 40
            and "uncertain" in record.message.lower()
            and (
                "timed out" in record.message.lower()
                or "deadline" in record.message.lower()
            )
            for record in caplog.records
        )

    finally:
        claims.release.set()

        try:
            await asyncio.wait_for(
                claims.finished.wait(),
                timeout=5,
            )
        except asyncio.TimeoutError:
            pytest.fail(
                "Uncertainty transition did not finish "
                "after being released"
            )

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    assert claims.records[
        ("tenant-a", "timeout-transition-test")
    ].state == "uncertain"

@pytest.mark.asyncio
async def test_orphaned_in_progress_claim_is_not_reexecuted() -> None:
    from core.resilience.request_fingerprint import (
        make_request_fingerprint,
    )

    claims = FakeClaimRepository()
    coordinator = ToolExecutionCoordinator(claims)

    tenant = "tenant-a"
    key = "orphaned-send-message"
    tool = "whatsapp.send_message"
    payload = {"recipient": "+971500000000", "message": "Hello"}

    fingerprint = make_request_fingerprint(
        tenant, tool, payload
    )

    # Simulate a previous worker acquiring ownership, then
    # disappearing without completing or resolving the claim.
    original_owner = await claims.claim(
        tenant, key, tool, fingerprint
    )
    assert original_owner is not None

    calls = 0

    async def action() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"message_id": "duplicate"}

    for _ in range(3):
        result = await coordinator.execute(
            tenant, key, tool, action, payload=payload
        )
        assert result.status == CoordinationStatus.IN_PROGRESS
        assert result.data is None

    assert calls == 0

    record = await claims.get(tenant, key)
    assert record is not None
    assert record.state == "in_progress"
    assert record.owner_token == original_owner


@pytest.mark.asyncio
async def test_uncertain_claim_requires_reconciliation_no_retry() -> None:
    from core.resilience.request_fingerprint import (
        make_request_fingerprint,
    )

    claims = FakeClaimRepository()
    coordinator = ToolExecutionCoordinator(claims)

    tenant = "tenant-a"
    key = "unresolved-external-action"
    tool = "crm.create_lead"
    payload = {"name": "Example Lead"}

    fingerprint = make_request_fingerprint(
        tenant, tool, payload
    )

    owner = await claims.claim(
        tenant, key, tool, fingerprint
    )
    assert owner is not None

    assert await claims.mark_uncertain(
        tenant, key, owner
    )

    calls = 0

    async def action() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"lead_id": "duplicate"}

    for _ in range(3):
        result = await coordinator.execute(
            tenant, key, tool, action, payload=payload
        )
        assert result.status == CoordinationStatus.UNCERTAIN
        assert result.data is None

    assert calls == 0
