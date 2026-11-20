from __future__ import annotations

from typing import ClassVar

from agents.base.agent import AgentSpec, BaseAgent
from agents.base.context import ExecutionContext
from agents.qualification.schemas import QualificationInput, QualificationResult
from schemas.agents.models import ImplementationStatus
from schemas.leads.models import (
    LeadPurpose,
    LeadRouting,
    LeadScore,
    LeadStatus,
    QualificationCategory,
)

_ROUTING: dict[QualificationCategory, tuple[str, str]] = {
    QualificationCategory.HOT: ("sales-priority", "p1"),
    QualificationCategory.WARM: ("sales", "p2"),
    QualificationCategory.NURTURE: ("nurture", "p3"),
    QualificationCategory.COLD: ("nurture", "p3"),
    QualificationCategory.DISQUALIFIED: ("review", "p3"),
}


def route(score: LeadScore, purpose: LeadPurpose) -> LeadRouting:
    if purpose == LeadPurpose.RENT:
        return LeadRouting(queue="leasing", priority="p3", reason="Rental enquiry")
    queue, priority = _ROUTING[score.category]
    return LeadRouting(
        queue=queue, priority=priority, reason=f"{score.category.value} lead (score {score.score})"
    )


class QualificationAgent(BaseAgent[QualificationInput, QualificationResult]):
    spec: ClassVar[AgentSpec] = AgentSpec(
        agent_id="qualification",
        name="Lead Qualification Agent",
        description="Scores leads with explainable factors and assigns a category and route.",
        responsibilities=[
            "Analyze buying or investment intent",
            "Evaluate lead readiness and budget",
            "Generate explainable lead scores",
            "Assign qualification categories and routing",
        ],
        implementation_status=ImplementationStatus.FUNCTIONAL,
        allowed_tools=frozenset({"analytics.score_lead"}),
        status_notes="Rules-based scoring (rules-v1); weights need calibration on real outcomes.",
    )
    input_model = QualificationInput
    output_model = QualificationResult

    async def execute(self, data: QualificationInput, ctx: ExecutionContext) -> QualificationResult:
        result = await self.use_tool(
            ctx, "analytics.score_lead", {"lead": data.lead.model_dump(mode="json")}
        )
        score = LeadScore.model_validate(result.data)
        status = (
            LeadStatus.QUALIFIED
            if score.category
            in {
                QualificationCategory.HOT,
                QualificationCategory.WARM,
            }
            else LeadStatus.NURTURING
        )
        return QualificationResult(
            lead_id=data.lead.lead_id,
            score=score,
            routing=route(score, data.lead.purpose),
            status=status,
        )
