"""Workflow execution and saved history retain their original organization."""

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel, Field

from core.exceptions.errors import AuthorizationError, ConflictError, DomainValidationError
from schemas.agents.models import ImplementationStatus
from workflows.engine.core import (
    InMemoryWorkflowRunStore,
    Step,
    StepOutcome,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStatus,
)
from workflows.registry import WORKFLOWS


class FictionalState(BaseModel):
    notes: list[str] = Field(default_factory=lambda: ["Original fictional state"])


def definition(handler, *, key="fictional_history_scope"):
    return WorkflowDefinition(
        workflow_id=key,
        name="Fictional history fixture",
        description="No external writes",
        implementation_status=ImplementationStatus.FUNCTIONAL,
        state_model=FictionalState,
        steps=(Step("fictional_step", handler),),
    )


def fixture_run(**changes):
    return WorkflowRun(
        execution_id="fictional-shared-execution-id",
        workflow_id="fictional_history_scope",
        tenant_id="owner-org",
        correlation_id="fictional-history-ownership",
        state={"notes": ["Original fictional state"]},
        **changes,
    )


@pytest.mark.parametrize("workflow_id", sorted(WORKFLOWS))
async def test_registered_workflows_reject_foreign_context_before_parsing_or_save(
    runtime, ctx, monkeypatch, workflow_id
):
    save = AsyncMock()
    monkeypatch.setattr(runtime.runner.store, "save", save)
    with pytest.raises(AuthorizationError):
        await runtime.runner.run(WORKFLOWS[workflow_id], {}, replace(ctx, tenant_id="other-org"))
    save.assert_not_awaited()


async def test_mismatched_context_cannot_reach_a_non_agent_step(runtime, ctx):
    step = AsyncMock(return_value=StepOutcome.CONTINUE)
    with pytest.raises(AuthorizationError):
        await runtime.runner.run(
            definition(step), FictionalState(), replace(ctx, tenant_id="other-org")
        )
    step.assert_not_awaited()
    assert runtime.runner.store.runs == {}


async def test_execution_id_cannot_replace_foreign_history():
    store = InMemoryWorkflowRunStore()
    original = fixture_run()
    await store.save(original)
    foreign = original.model_copy(deep=True, update={"tenant_id": "other-org"})
    with pytest.raises(AuthorizationError):
        await store.save(foreign)
    assert store.runs[original.execution_id] == original


async def test_execution_id_cannot_change_workflow_identity():
    store = InMemoryWorkflowRunStore()
    original = fixture_run()
    await store.save(original)
    changed = original.model_copy(deep=True, update={"workflow_id": "fictional_other_workflow"})
    with pytest.raises(ConflictError):
        await store.save(changed)
    assert store.runs[original.execution_id] == original


@pytest.mark.parametrize("mutation", ["input", "output"])
async def test_history_snapshots_cannot_reassign_owner_or_state(mutation):
    store = InMemoryWorkflowRunStore()
    original = fixture_run()
    expected = original.model_copy(deep=True)
    await store.save(original)
    target = original if mutation == "input" else store.runs[original.execution_id]
    target.tenant_id = "other-org"
    target.state["notes"].append("Changed outside save")
    assert store.runs[expected.execution_id] == expected


@pytest.mark.parametrize(
    "outcome",
    ["continue", "complete", "pending_approval", "escalate", "domain_failure", "internal_failure"],
)
async def test_each_run_outcome_has_detached_owned_history(runtime, ctx, outcome):
    async def step(state, _):
        state.notes.append("Fictional step executed")
        if outcome == "domain_failure":
            raise DomainValidationError("Fictional step failure")
        if outcome == "internal_failure":
            raise RuntimeError("Fictional unexpected failure")
        return StepOutcome(outcome)

    run, state = await runtime.runner.run(definition(step), FictionalState(), ctx)
    expected_status = {
        "continue": "succeeded",
        "complete": "succeeded",
        "pending_approval": "pending_approval",
        "escalate": "escalated",
        "domain_failure": "failed",
        "internal_failure": "failed",
    }[outcome]
    assert run.status == expected_status and run.tenant_id == ctx.tenant_id
    assert state.notes[-1] == "Fictional step executed"
    expected = run.model_copy(deep=True)
    run.tenant_id = "other-org"
    run.state["notes"].clear()
    run.steps.clear()
    state.notes.clear()
    assert runtime.runner.store.runs[expected.execution_id] == expected


async def test_same_owner_and_workflow_can_save_an_update():
    store = InMemoryWorkflowRunStore()
    run = fixture_run()
    await store.save(run)
    run.status = WorkflowStatus.SUCCEEDED
    run.state["notes"].append("Explicit saved update")
    await store.save(run)
    assert store.runs[run.execution_id] == run
    assert len(store.runs) == 1


async def test_history_retention_remains_bounded_and_returned_mapping_is_detached():
    store = InMemoryWorkflowRunStore(max_runs=2)
    for index in range(3):
        await store.save(
            fixture_run().model_copy(update={"execution_id": f"fictional-run-{index}"})
        )
    view = store.runs
    assert list(view) == ["fictional-run-1", "fictional-run-2"]
    view.clear()
    assert len(store.runs) == 2
