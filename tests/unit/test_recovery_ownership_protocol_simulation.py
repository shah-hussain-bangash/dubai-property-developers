
"""Model-level tests for PostgreSQL/Redis recovery ownership.

Development-only simulation.

No PostgreSQL, Redis, Docker, background workers, or real
queues are accessed.

These tests demonstrate the existing publication race and
define the safety requirement for a future handoff protocol.

Passing diagnostic tests do NOT prove that the production
system satisfies the safety requirement.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass
class RecoveryState:
    """Minimal model of two independent ownership records."""

    postgres_generation: int = 1
    redis_generation: int = 1
    reservation_in_processing: bool = True
    reservation_in_pending: bool = False
    evidence_present: bool = False

    def postgres_takeover(self) -> None:
        """Coordinator B claims ownership in PostgreSQL."""
        self.postgres_generation += 1

    def publish_redis_generation(self) -> None:
        """Publish the latest PostgreSQL generation to Redis."""
        self.redis_generation = self.postgres_generation

    def redis_transition(self, generation: int) -> str:
        """Model current Redis-only generation comparison."""

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


def test_current_owner_can_move_before_takeover():
    state = RecoveryState()

    assert state.redis_transition(1) == "moved"
    assert state.reservation_in_pending is True
    assert state.evidence_present is True


def test_stale_owner_rejected_after_redis_publication():
    state = RecoveryState()

    state.postgres_takeover()
    state.publish_redis_generation()

    assert state.redis_transition(1) == "stale"
    assert state.reservation_in_processing is True


def test_publication_gap_allows_old_owner_to_move():
    """Document the known unsafe sequence."""

    state = RecoveryState()

    state.postgres_takeover()

    assert state.postgres_generation == 2
    assert state.redis_generation == 1

    # This is the known unsafe outcome.
    assert state.redis_transition(1) == "moved"

    assert state.reservation_in_pending is True
    assert state.evidence_present is True


def test_replay_does_not_duplicate_transition():
    state = RecoveryState()

    assert state.redis_transition(1) == "moved"
    assert state.redis_transition(1) == "already_moved"


def test_missing_reservation_does_not_create_job():
    state = RecoveryState(
        reservation_in_processing=False,
    )

    assert state.redis_transition(1) == "missing"
    assert state.reservation_in_pending is False


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Current Redis-only fencing cannot reject generation 1 "
        "when PostgreSQL is at generation 2 but Redis is still at 1"
    ),
)
def test_required_stale_rejection_during_publication_gap():
    """Future protocol must reject stale ownership."""

    state = RecoveryState()

    state.postgres_takeover()

    assert state.redis_transition(1) == "stale"
    assert state.reservation_in_processing is True
    assert state.reservation_in_pending is False
