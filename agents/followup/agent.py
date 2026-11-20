from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from agents.base.agent import AgentSpec, BaseAgent
from agents.base.context import ExecutionContext
from agents.followup.schemas import (
    FollowUpAction,
    FollowUpInput,
    FollowUpPlan,
    FollowUpTask,
    SkippedTask,
)
from core.exceptions.errors import PlatformError
from schemas.agents.models import AgentRunStatus, ImplementationStatus
from schemas.conversations.models import Channel
from tools.base import ToolResultStatus

MAX_ATTEMPTS = 3
OVERDUE_ESCALATION = timedelta(hours=48)
# Outside the 24h window WhatsApp requires a template pre-approved by Meta. This name must
# match a template registered on the WhatsApp Business account before going live.
WHATSAPP_FOLLOWUP_TEMPLATE = "follow_up_generic"


class FollowUpAgent(BaseAgent[FollowUpInput, FollowUpPlan]):
    spec: ClassVar[AgentSpec] = AgentSpec(
        agent_id="followup",
        name="Follow-Up Agent",
        description="Finds due follow-ups, checks consent, prepares drafts and requests approved sends.",
        responsibilities=[
            "Track follow-up schedules",
            "Identify unanswered enquiries",
            "Prepare follow-up messages",
            "Request approval-gated sends",
            "Escalate overdue sales activities",
        ],
        implementation_status=ImplementationStatus.PARTIAL,
        allowed_tools=frozenset({"email.render_template", "email.send", "whatsapp.send_message"}),
        status_notes="Planning + approval-gated dispatch work with mocks; DB task source and "
        "scheduled worker trigger pending.",
    )
    input_model = FollowUpInput
    output_model = FollowUpPlan

    def _check(self, task: FollowUpTask, now: datetime) -> SkippedTask | None:
        if task.status != "open":
            return SkippedTask(task_id=task.task_id, reason=f"status is {task.status}")
        if task.customer_replied_since:
            return SkippedTask(task_id=task.task_id, reason="customer already replied")
        if task.due_at > now:
            return SkippedTask(task_id=task.task_id, reason="not yet due")
        if task.channel == Channel.WHATSAPP and not (task.consent_whatsapp and task.to_e164):
            return SkippedTask(task_id=task.task_id, reason="no WhatsApp opt-in or number")
        if task.channel == Channel.EMAIL and not task.email:
            return SkippedTask(task_id=task.task_id, reason="no email address")
        if task.channel not in {Channel.WHATSAPP, Channel.EMAIL}:
            return SkippedTask(task_id=task.task_id, reason=f"channel {task.channel.value} not automated")
        return None

    def _send_request(self, task: FollowUpTask, subject: str, body: str) -> tuple[str, dict[str, Any]]:
        key = f"followup:{task.task_id}:{task.attempts}"
        if task.channel == Channel.WHATSAPP:
            return "whatsapp.send_message", {
                "to_e164": task.to_e164,
                "consent_whatsapp": task.consent_whatsapp,
                "last_inbound_at": task.last_inbound_at.isoformat() if task.last_inbound_at else None,
                "template_name": WHATSAPP_FOLLOWUP_TEMPLATE,
                "language_code": "en",
                "idempotency_key": key,
            }
        return "email.send", {
            "to": task.email,
            "subject": subject,
            "body": body,
            "is_marketing": False,
            "idempotency_key": key,
        }

    async def execute(self, data: FollowUpInput, ctx: ExecutionContext) -> FollowUpPlan:
        now = data.now or datetime.now(UTC)
        plan = FollowUpPlan()
        for task in data.tasks:
            skip = self._check(task, now)
            if skip:
                plan.skipped.append(skip)
                continue
            if task.attempts >= MAX_ATTEMPTS:
                plan.escalations.append(
                    SkippedTask(task_id=task.task_id, reason="max automated attempts reached")
                )
                continue
            if now - task.due_at > OVERDUE_ESCALATION:
                plan.escalations.append(SkippedTask(task_id=task.task_id, reason="overdue by more than 48h"))
            rendered = await self.use_tool(
                ctx,
                "email.render_template",
                {
                    "template": "follow_up_generic",
                    "values": {"first_name": task.contact_first_name, "advisor_name": "Your advisor"},
                },
            )
            action = FollowUpAction(
                task_id=task.task_id,
                lead_id=task.lead_id,
                channel=task.channel,
                template=WHATSAPP_FOLLOWUP_TEMPLATE,
                draft_text=rendered.data["body"],
            )
            if data.dispatch:
                tool, payload = self._send_request(task, rendered.data["subject"], rendered.data["body"])
                try:
                    sent = await self.use_tool(ctx, tool, payload, reason=f"Follow-up for task {task.task_id}")
                    action.send_status = sent.status.value
                    action.approval_id = sent.approval_id
                except PlatformError as exc:  # one failing task must not block the batch
                    action.error = exc.code
            plan.actions.append(action)
        return plan

    def outcome_status(self, output: FollowUpPlan) -> AgentRunStatus:
        if any(a.send_status == ToolResultStatus.PENDING_APPROVAL for a in output.actions):
            return AgentRunStatus.PENDING_APPROVAL
        if output.escalations:
            return AgentRunStatus.ESCALATED
        return AgentRunStatus.SUCCEEDED
