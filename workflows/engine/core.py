"""Deterministic, typed workflow engine.

A workflow is an ordered list of named async steps operating on a typed Pydantic
state. The runner records every step, stops on approval/escalation outcomes and
maps errors to a structured failed run. It is framework-free on purpose: steps
could later be hosted by LangGraph without changing business logic.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel, Field

from agents.base.agent import AgentResult
from agents.base.context import ExecutionContext
from agents.registry import AgentRegistry
from core.exceptions.errors import PlatformError, WorkflowError
from core.observability.logging import get_logger
from schemas.agents.models import AgentRunStatus, ImplementationStatus

logger = get_logger("workflows")
StateT = TypeVar("StateT", bound=BaseModel)


class StepOutcome(StrEnum):
    CONTINUE = "continue"
    COMPLETE = "complete"  # finish successfully, skipping remaining steps
    PENDING_APPROVAL = "pending_approval"
    ESCALATE = "escalate"


class WorkflowStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PENDING_APPROVAL = "pending_approval"
    ESCALATED = "escalated"


class StepRecord(BaseModel):
    name: str
    outcome: str
    duration_ms: int
    error_code: str | None = None


class WorkflowRun(BaseModel):
    execution_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    workflow_id: str
    tenant_id: str
    correlation_id: str
    status: WorkflowStatus = WorkflowStatus.RUNNING
    current_step: str | None = None
    steps: list[StepRecord] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


class WorkflowDescriptor(BaseModel):
    workflow_id: str
    name: str
    description: str
    steps: list[str]
    implementation_status: ImplementationStatus


@dataclass
class WorkflowContext:
    execution: ExecutionContext
    agents: AgentRegistry

    async def run_agent(self, agent_id: str, payload: BaseModel | dict[str, Any]) -> AgentResult:
        result = await self.agents.get(agent_id).run(payload, self.execution)
        if not result.ok:
            error = result.error
            raise WorkflowError(
                f"agent '{agent_id}' {result.status.value}",
                details={"agent_id": agent_id, "agent_error": error.model_dump() if error else None},
            )
        return result


StepHandler = Callable[[Any, WorkflowContext], Awaitable[StepOutcome]]


@dataclass(frozen=True, slots=True)
class Step:
    name: str
    handler: StepHandler


@dataclass(frozen=True)
class WorkflowDefinition(Generic[StateT]):
    workflow_id: str
    name: str
    description: str
    implementation_status: ImplementationStatus
    state_model: type[StateT]
    steps: tuple[Step, ...]

    def descriptor(self) -> WorkflowDescriptor:
        return WorkflowDescriptor(
            workflow_id=self.workflow_id,
            name=self.name,
            description=self.description,
            steps=[s.name for s in self.steps],
            implementation_status=self.implementation_status,
        )


class WorkflowRunStore(Protocol):
    async def save(self, run: WorkflowRun) -> None: ...


class InMemoryWorkflowRunStore:
    def __init__(self, max_runs: int = 500) -> None:
        self.runs: dict[str, WorkflowRun] = {}
        self._max = max_runs

    async def save(self, run: WorkflowRun) -> None:
        self.runs[run.execution_id] = run
        while len(self.runs) > self._max:
            self.runs.pop(next(iter(self.runs)))


_TERMINAL = {
    StepOutcome.PENDING_APPROVAL: WorkflowStatus.PENDING_APPROVAL,
    StepOutcome.ESCALATE: WorkflowStatus.ESCALATED,
    StepOutcome.COMPLETE: WorkflowStatus.SUCCEEDED,
}


class WorkflowRunner:
    def __init__(self, agents: AgentRegistry, store: WorkflowRunStore | None = None) -> None:
        self._agents = agents
        self.store: WorkflowRunStore = store or InMemoryWorkflowRunStore()

    async def run(
        self,
        definition: WorkflowDefinition[StateT],
        initial: StateT | dict[str, Any],
        ctx: ExecutionContext,
    ) -> tuple[WorkflowRun, StateT]:
        state = (
            initial
            if isinstance(initial, definition.state_model)
            else definition.state_model.model_validate(initial)
        )
        run = WorkflowRun(
            workflow_id=definition.workflow_id, tenant_id=ctx.tenant_id, correlation_id=ctx.correlation_id
        )
        wctx = WorkflowContext(
            execution=ExecutionContext(
                principal=ctx.principal,
                tenant_id=ctx.tenant_id,
                correlation_id=ctx.correlation_id,
                workflow_execution_id=run.execution_id,
            ),
            agents=self._agents,
        )
        logger.info("workflow started", extra={"workflow_id": definition.workflow_id})
        for step in definition.steps:
            run.current_step = step.name
            started = time.perf_counter()
            try:
                outcome = await step.handler(state, wctx)
            except PlatformError as exc:
                run.steps.append(StepRecord(name=step.name, outcome="failed", duration_ms=_ms(started), error_code=exc.code))
                run.status = WorkflowStatus.FAILED
                run.error = exc.to_dict()
                break
            except Exception as exc:
                logger.exception("workflow step crashed", extra={"step": step.name})
                run.steps.append(
                    StepRecord(name=step.name, outcome="failed", duration_ms=_ms(started), error_code="internal_error")
                )
                run.status = WorkflowStatus.FAILED
                run.error = {"code": "internal_error", "message": type(exc).__name__, "details": {}}
                break
            run.steps.append(StepRecord(name=step.name, outcome=outcome.value, duration_ms=_ms(started)))
            if outcome in _TERMINAL:
                run.status = _TERMINAL[outcome]
                break
        else:
            run.status = WorkflowStatus.SUCCEEDED
        run.finished_at = datetime.now(UTC)
        run.state = state.model_dump(mode="json")
        await self.store.save(run)
        logger.info(
            "workflow finished",
            extra={"workflow_id": definition.workflow_id, "status": run.status.value},
        )
        return run, state


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def outcome_for(result: AgentResult) -> StepOutcome:
    if result.status == AgentRunStatus.PENDING_APPROVAL:
        return StepOutcome.PENDING_APPROVAL
    if result.status == AgentRunStatus.ESCALATED:
        return StepOutcome.ESCALATE
    return StepOutcome.CONTINUE
