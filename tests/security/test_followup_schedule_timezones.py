"""Follow-up scheduling compares equivalent timestamps without losing a batch."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from agents.followup.schemas import FollowUpInput
from workflows.followup_flow import FOLLOWUP_AUTOMATION, FollowUpFlowState
from workflows.runtime import build_runtime

TEXT = "Fictional garden policy allows two visits."


@pytest.fixture(params=[False, True], ids=["fixture-mode", "source-only"])
async def followup_runtime(request, settings, tmp_path, ctx):
    if request.param:
        settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    runtime = build_runtime(settings)
    await runtime.initialize()
    if runtime.assigned_sources is not None:
        runtime.assigned_sources.add(
            ctx.tenant_id, "followup", "Fictional garden policy", "text", [TEXT], customer_safe=True
        )
    try:
        yield runtime
    finally:
        await runtime.shutdown()


def task(due, task_id="fictional-due-task", **changes):
    return {
        "task_id": task_id,
        "lead_id": "fictional-lead",
        "contact_first_name": "Fictional Visitor",
        "channel": "email",
        "email": "fixture@example.com",
        "due_at": due.isoformat(),
        "knowledge_query": "garden policy",
        **changes,
    }


@pytest.mark.parametrize("form", ["naive-due", "naive-now", "both-naive", "offset"])
async def test_equivalent_utc_representations_prepare_same_due_action(followup_runtime, ctx, form):
    now = datetime.now(UTC)
    due = now - timedelta(hours=1)
    current = now
    if form in {"naive-due", "both-naive"}:
        due = due.replace(tzinfo=None)
    if form in {"naive-now", "both-naive"}:
        current = now.replace(tzinfo=None)
    if form == "offset":
        due = due.astimezone(timezone(timedelta(hours=4)))
    result = await followup_runtime.agents.get("followup").run(
        {"tasks": [task(due)], "now": current.isoformat()}, ctx
    )
    assert result.status == "succeeded", result.error
    assert [action.task_id for action in result.output.actions] == ["fictional-due-task"]
    assert result.output.skipped == result.output.escalations == []


@pytest.mark.parametrize(
    "delta,actions,escalations",
    [
        (timedelta(0), 1, 0),
        (timedelta(minutes=1), 0, 0),
        (-timedelta(hours=48), 1, 0),
        (-timedelta(hours=48, seconds=1), 1, 1),
    ],
)
async def test_due_and_overdue_boundaries_remain_exact(
    followup_runtime, ctx, delta, actions, escalations
):
    now = datetime.now(UTC)
    due = (now + delta).replace(tzinfo=None)
    result = await followup_runtime.agents.get("followup").run(
        {"tasks": [task(due)], "now": now.isoformat()}, ctx
    )
    assert result.status == ("escalated" if escalations else "succeeded"), result.error
    assert len(result.output.actions) == actions
    assert len(result.output.escalations) == escalations
    if not actions:
        assert result.output.skipped[0].reason == "not yet due"


async def test_mixed_batch_keeps_valid_tasks_and_future_skip(followup_runtime, ctx):
    now = datetime.now(UTC)
    tasks = [
        task(now - timedelta(hours=1), "fictional-aware"),
        task((now - timedelta(hours=2)).replace(tzinfo=None), "fictional-naive"),
        task(
            (now + timedelta(hours=1)).astimezone(timezone(timedelta(hours=4))), "fictional-future"
        ),
    ]
    result = await followup_runtime.agents.get("followup").run(
        {"tasks": tasks, "now": now.isoformat()}, ctx
    )
    assert result.status == "succeeded", result.error
    assert [action.task_id for action in result.output.actions] == [
        "fictional-aware",
        "fictional-naive",
    ]
    assert [item.task_id for item in result.output.skipped] == ["fictional-future"]


async def test_default_clock_accepts_legacy_naive_utc_task(followup_runtime, ctx):
    due = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
    result = await followup_runtime.agents.get("followup").run({"tasks": [task(due)]}, ctx)
    assert result.status == "succeeded" and len(result.output.actions) == 1


async def test_scheduling_does_not_rewrite_supplied_models(followup_runtime, ctx):
    now = datetime.now(UTC).replace(tzinfo=None)
    data = FollowUpInput.model_validate(
        {"tasks": [task(now - timedelta(hours=1))], "now": now.isoformat()}
    )
    expected = data.model_dump(mode="json")
    result = await followup_runtime.agents.get("followup").run(data, ctx)
    assert result.status == "succeeded"
    assert data.model_dump(mode="json") == expected


async def test_workflow_queues_then_sends_once_after_approval(followup_runtime, ctx):
    now = datetime.now(UTC)
    state = FollowUpFlowState.model_validate(
        {
            "request": {
                "tasks": [task((now - timedelta(hours=1)).replace(tzinfo=None))],
                "now": now.isoformat(),
            }
        }
    )
    run, final = await followup_runtime.runner.run(FOLLOWUP_AUTOMATION, state, ctx)
    assert run.status == "pending_approval", run.error
    assert followup_runtime.email_sender.outbox == []
    approval = final.plan.actions[0].approval_id
    await followup_runtime.approvals.decide(
        approval, approved=True, decided_by=ctx.principal.subject
    )
    first = await followup_runtime.gateway.execute_approved(approval, ctx.principal)
    replay = await followup_runtime.gateway.execute_approved(approval, ctx.principal)
    assert first.data == replay.data and replay.status == "replayed"
    assert len(followup_runtime.email_sender.outbox) == 1
    if followup_runtime.assigned_sources is not None:
        assert followup_runtime.email_sender.outbox[0]["body"] == TEXT
