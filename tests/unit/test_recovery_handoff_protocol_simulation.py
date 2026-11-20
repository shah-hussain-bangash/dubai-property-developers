
"""Simulation of a Redis-first recovery ownership handoff.

Development-only. No external services are accessed.

The protocol requires all participating coordinators to use
the same Redis gate before PostgreSQL ownership changes.

This simulation tests modeled ordering and safety properties.
It does NOT establish a crash-safe distributed protocol or
prove that existing PostgreSQL/Redis implementations are safe.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass
class HandoffState:
    postgres_generation: int = 1
    redis_generation: int | None = 1
    redis_gate_open: bool = True
    reservation_in_processing: bool = True
    reservation_in_pending: bool = False
    evidence_present: bool = False

    def close_redis_gate(self) -> None:
        """Prevent all modeled Redis recovery transitions."""
        self.redis_gate_open = False

    def postgres_takeover(self) -> None:
        """Model a PostgreSQL ownership transfer."""
        self.postgres_generation += 1

    def publish_new_generation(self) -> None:
        """Publish PostgreSQL generation while gate is closed."""
        if self.redis_gate_open:
            raise RuntimeError(
                "Cannot publish while Redis gate is open"
            )

        self.redis_generation = self.postgres_generation

    def open_redis_gate(self) -> None:
        """Reopen only if Redis and PostgreSQL generations agree."""
        if self.redis_generation != self.postgres_generation:
            raise RuntimeError(
                "Generation mismatch prevents opening gate"
            )

        self.redis_gate_open = True

    def redis_transition(self, generation: int) -> str:
        """Model a generation-fenced queue transition."""
        if not self.redis_gate_open:
            return "blocked"

        if self.redis_generation is None:
            return "uninitialized"

        if generation != self.redis_generation:
            return "stale"

        if self.evidence_present:
            return "already_moved"

        if not self.reservation_in_processing:
            return "missing"

        if self.reservation_in_pending:
            return "ambiguous"

        self.reservation_in_processing = False
        self.reservation_in_pending = True
        self.evidence_present = True

        return "moved"


def test_current_owner_can_move_before_handoff():
    state = HandoffState()

    assert state.redis_transition(1) == "moved"


def test_closed_gate_blocks_old_coordinator():
    state = HandoffState()

    state.close_redis_gate()

    assert state.redis_transition(1) == "blocked"
    assert state.reservation_in_processing is True


def test_closed_gate_blocks_new_coordinator():
    state = HandoffState()

    state.close_redis_gate()
    state.postgres_takeover()

    assert state.redis_transition(2) == "blocked"


def test_completed_handoff_rejects_old_generation():
    state = HandoffState()

    state.close_redis_gate()
    state.postgres_takeover()
    state.publish_new_generation()
    state.open_redis_gate()

    assert state.redis_transition(1) == "stale"
    assert state.redis_transition(2) == "moved"


def test_crash_after_gate_closure_stays_blocked():
    state = HandoffState()

    state.close_redis_gate()

    # Simulate coordinator crash: no more handoff calls.
    assert state.redis_transition(1) == "blocked"


def test_crash_after_postgres_takeover_stays_blocked():
    state = HandoffState()

    state.close_redis_gate()
    state.postgres_takeover()

    # Redis publication never occurs.
    assert state.redis_transition(1) == "blocked"
    assert state.redis_transition(2) == "blocked"


def test_crash_after_publication_stays_blocked():
    state = HandoffState()

    state.close_redis_gate()
    state.postgres_takeover()
    state.publish_new_generation()

    assert state.redis_transition(1) == "blocked"
    assert state.redis_transition(2) == "blocked"


def test_generation_mismatch_prevents_gate_open():
    state = HandoffState()

    state.close_redis_gate()
    state.postgres_takeover()

    with pytest.raises(
        RuntimeError,
        match="Generation mismatch",
    ):
        state.open_redis_gate()


def test_publication_requires_closed_gate():
    state = HandoffState()

    with pytest.raises(
        RuntimeError,
        match="gate is open",
    ):
        state.publish_new_generation()


def test_missing_redis_generation_fails_closed():
    state = HandoffState(redis_generation=None)

    assert state.redis_transition(1) == "uninitialized"


def test_delayed_old_command_rejected_after_handoff():
    state = HandoffState()

    # Old coordinator has already prepared generation 1.
    delayed_generation = 1

    state.close_redis_gate()
    state.postgres_takeover()
    state.publish_new_generation()
    state.open_redis_gate()

    assert state.redis_transition(delayed_generation) == "stale"
    assert state.reservation_in_processing is True


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Existing PostgreSQL claim API does not require "
        "the Redis gate to be closed before ownership transfer"
    ),
)
def test_existing_ungated_takeover_must_be_rejected():
    """Safety requirement missing from the current implementation."""
    state = HandoffState()

    # Existing behavior permits direct PostgreSQL takeover.
    state.postgres_takeover()

    # Required protocol behavior would reject this transfer.
    assert state.postgres_generation == 1


@pytest.mark.xfail(
    strict=True,
    reason=(
        "A volatile Redis gate can be lost or reverted without "
        "a durable cross-system ownership handoff"
    ),
)
def test_redis_gate_loss_must_not_reauthorize_old_owner():
    """Model a gate that disappears/reverts during takeover."""
    state = HandoffState()

    state.close_redis_gate()
    state.postgres_takeover()

    # Simulate Redis state restoration to old values.
    state.redis_generation = 1
    state.redis_gate_open = True

    # Required safety: old command must remain blocked.
    assert state.redis_transition(1) != "moved"
