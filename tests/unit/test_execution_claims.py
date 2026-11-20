from __future__ import annotations

import asyncio

import pytest

from core.resilience.execution_claims import (
    ExecutionState,
    InMemoryExecutionClaimStore,
)


@pytest.mark.asyncio
async def test_only_one_concurrent_claim_succeeds() -> None:
    store = InMemoryExecutionClaimStore()

    claims = await asyncio.gather(*(store.claim("tenant-a:action-1") for _ in range(20)))

    assert sum(claim is not None for claim in claims) == 1


@pytest.mark.asyncio
async def test_different_keys_can_be_claimed() -> None:
    store = InMemoryExecutionClaimStore()

    first, second = await asyncio.gather(
        store.claim("tenant-a:action-1"),
        store.claim("tenant-a:action-2"),
    )

    assert first is not None
    assert second is not None
    assert first.owner_token != second.owner_token


@pytest.mark.asyncio
async def test_only_owner_can_complete() -> None:
    store = InMemoryExecutionClaimStore()

    claim = await store.claim("tenant-a:action-1")
    assert claim is not None

    with pytest.raises(PermissionError):
        await store.complete(
            claim.key,
            "wrong-owner",
            {"message_id": "123"},
        )

    completed = await store.complete(
        claim.key,
        claim.owner_token,
        {"message_id": "123"},
    )

    assert completed.state == ExecutionState.COMPLETED
    assert completed.result == {"message_id": "123"}


@pytest.mark.asyncio
async def test_completed_action_cannot_be_claimed_again() -> None:
    store = InMemoryExecutionClaimStore()

    claim = await store.claim("tenant-a:action-1")
    assert claim is not None

    await store.complete(
        claim.key,
        claim.owner_token,
        {"message_id": "123"},
    )

    assert await store.claim(claim.key) is None


@pytest.mark.asyncio
async def test_uncertain_action_cannot_be_reclaimed() -> None:
    store = InMemoryExecutionClaimStore()

    claim = await store.claim("tenant-a:action-1")
    assert claim is not None

    uncertain = await store.mark_uncertain(
        claim.key,
        claim.owner_token,
    )

    assert uncertain.state == ExecutionState.UNCERTAIN
    assert await store.claim(claim.key) is None


@pytest.mark.asyncio
async def test_stale_owner_cannot_change_completed_state() -> None:
    store = InMemoryExecutionClaimStore()

    claim = await store.claim("tenant-a:action-1")
    assert claim is not None

    await store.complete(
        claim.key,
        claim.owner_token,
        {"message_id": "123"},
    )

    with pytest.raises(ValueError):
        await store.mark_uncertain(
            claim.key,
            claim.owner_token,
        )
