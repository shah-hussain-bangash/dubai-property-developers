"""Workflow 05 - CRM Synchronization (partial).

External Event -> Validate -> Match Record -> Resolve Conflicts -> Update -> Audit

Conflict policy: if the local record changed after the last successful sync AND
the external change is not newer than the local change, mark CONFLICT for human
review; otherwise the newer change wins. Persistence of sync records
(``external_sync_records``) is pending.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from core.events.bus import DomainEvent
from core.exceptions.errors import DomainValidationError
from schemas.agents.models import ImplementationStatus
from schemas.events.models import ExternalRecordEvent, SyncOperation
from workflows.engine.core import Step, StepOutcome, WorkflowContext, WorkflowDefinition

SUPPORTED_SOURCES = {"espocrm"}
SUPPORTED_ENTITIES = {"lead", "contact", "opportunity"}


class SyncDecision(StrEnum):
    APPLY_EXTERNAL = "apply_external"
    KEEP_LOCAL = "keep_local"
    CONFLICT = "conflict"
    CREATE_LOCAL = "create_local"
    IGNORE = "ignore"


class LocalRecordSnapshot(BaseModel):
    local_id: str
    updated_at: datetime
    last_synced_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class CRMSyncState(BaseModel):
    event: ExternalRecordEvent
    local: LocalRecordSnapshot | None = None
    decision: SyncDecision | None = None
    changes: dict[str, Any] = Field(default_factory=dict)


def resolve(event: ExternalRecordEvent, local: LocalRecordSnapshot | None) -> SyncDecision:
    if event.operation == SyncOperation.DELETE:
        return SyncDecision.CONFLICT  # deletions always need human review
    if local is None:
        return SyncDecision.CREATE_LOCAL
    local_dirty = local.last_synced_at is None or local.updated_at > local.last_synced_at
    if not local_dirty:
        return SyncDecision.APPLY_EXTERNAL
    if event.occurred_at > local.updated_at:
        return SyncDecision.APPLY_EXTERNAL
    if event.occurred_at < local.updated_at:
        return SyncDecision.KEEP_LOCAL if not event.data else SyncDecision.CONFLICT
    return SyncDecision.CONFLICT


async def validate(state: CRMSyncState, ctx: WorkflowContext) -> StepOutcome:
    if state.event.source_system not in SUPPORTED_SOURCES:
        raise DomainValidationError(f"unsupported source {state.event.source_system}")
    if state.event.entity_type not in SUPPORTED_ENTITIES:
        raise DomainValidationError(f"unsupported entity {state.event.entity_type}")
    return StepOutcome.CONTINUE


async def match_and_resolve(state: CRMSyncState, ctx: WorkflowContext) -> StepOutcome:
    state.decision = resolve(state.event, state.local)
    if state.decision == SyncDecision.CONFLICT:
        return StepOutcome.ESCALATE
    return StepOutcome.CONTINUE


async def compute_update(state: CRMSyncState, ctx: WorkflowContext) -> StepOutcome:
    if state.decision in {SyncDecision.APPLY_EXTERNAL, SyncDecision.CREATE_LOCAL}:
        current = state.local.data if state.local else {}
        state.changes = {k: v for k, v in state.event.data.items() if current.get(k) != v}
    return StepOutcome.CONTINUE


async def audit(state: CRMSyncState, ctx: WorkflowContext) -> StepOutcome:
    crm_agent = ctx.agents.get("crm")
    await crm_agent.deps.events.publish(
        DomainEvent(
            event_type="crm.sync.processed",
            tenant_id=ctx.execution.tenant_id,
            payload={
                "external_id": state.event.external_id,
                "entity_type": state.event.entity_type,
                "decision": state.decision.value if state.decision else None,
                "changed_fields": sorted(state.changes),
            },
        )
    )
    return StepOutcome.CONTINUE


CRM_SYNC = WorkflowDefinition(
    workflow_id="crm_sync",
    name="CRM Synchronization",
    description="Validate external CRM events, match records, resolve conflicts, update and audit.",
    implementation_status=ImplementationStatus.PARTIAL,
    state_model=CRMSyncState,
    steps=(
        Step("validate", validate),
        Step("match_and_resolve_conflicts", match_and_resolve),
        Step("compute_update", compute_update),
        Step("audit", audit),
    ),
)
