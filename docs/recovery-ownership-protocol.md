
# Recovery Ownership and Fencing Protocol

Status: DESIGN ONLY — NOT APPROVED FOR PRODUCTION

## 1. Objective

Prevent unauthorized, stale, duplicated, or uncertain
Redis recovery transitions in the multi-agent platform.

## 2. Existing Components

- PostgreSQL JobRecoveryOperation
- PostgresRecoveryLeaseStore
- GuardedRecoveryTransition
- Redis recovery evidence Lua script
- Experimental Redis generation fencing
- Atomic Redis recovery snapshot inspector
- Recovery architecture isolation tests

## 3. Existing Safety Gaps

GAP-01: PostgreSQL ownership can advance before Redis
receives the new fencing generation.

GAP-02: Redis-only generation checks can authorize
commands submitted by an expired coordinator.

GAP-03: Redis recovery commands may execute after
the caller times out.

GAP-04: PostgreSQL completion currently depends on a
valid lease token, without mandatory Redis reconciliation
evidence verification in the repository method.

GAP-05: Redis fencing-key loss or restoration can
invalidate assumptions about ownership.

## 4. Required Safety Invariants

R1: A coordinator without current recovery authority
must not perform a new Redis recovery transition.

R2: Delayed commands must not bypass ownership fencing.

R3: Each operation must have idempotent recovery behavior.

R4: Inconsistent or missing evidence must fail closed.

R5: Completion requires authenticated, verified
reconciliation.

R6: Crashes must not silently restore stale authority.

R7: Tenant, job, attempt, and operation identity
must be validated before authorization.

## 5. Proposed Control Model

PostgreSQL remains authoritative for durable job state
and operation history.

Redis remains responsible for atomic queue transitions.

A future coordination mechanism must establish a
provable ordering between ownership changes and
Redis command authorization.

The current combination of PostgreSQL row locks and
Redis generation comparison is insufficient.

No recovery transition should be enabled until an
enforceable synchronization or single-authority
execution protocol is implemented.

## 6. Recovery Outcome Classification

- moved: Redis reports successful transition
- already_moved: Redis evidence indicates replay
- missing: reservation cannot be located
- ambiguous: duplicate/conflicting reservation state
- stale: command rejected by fencing
- uninitialized: Redis fencing state unavailable
- uncertain: evidence or system state cannot be trusted

All results require appropriate reconciliation.

## 7. Crash Scenarios to Test

C1: Crash before recovery authorization.

C2: Crash after ownership claim.

C3: Crash before Redis command execution.

C4: Redis executes but response is lost.

C5: PostgreSQL ownership transfers while a Redis
command is delayed.

C6: Redis restart or fencing-key loss.

C7: Crash after Redis transition but before PostgreSQL
completion.

C8: Concurrent coordinators attempt the same operation.

## 8. Production Activation Conditions

Automatic recovery must remain disabled until:

- The authoritative ownership protocol is implemented.
- All application recovery mutation paths enforce it.
- Previously failing safety requirements pass.
- Real PostgreSQL and Redis integration tests pass.
- Crash and timeout tests pass.
- Authenticated publication is enforced.
- Recovery completion requires reconciliation.
- Operational monitoring and failure alerts exist.
- The complete regression suite has no unexplained failures.

## 9. Current Baseline

419 passed, 5 expected failures, 2 warnings.

The expected failures document known safety gaps.

## 10. Implementation Rule

Do not mark the recovery protocol production-ready
based only on passing unit tests or simulations.

Any proposed implementation must explain how it
prevents stale Redis mutation across independent
PostgreSQL and Redis transaction boundaries.
