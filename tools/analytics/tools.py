from __future__ import annotations

from collections import Counter
from typing import Any, ClassVar

from core.exceptions.errors import AuthorizationError
from core.policies.actions import ActionCategory
from core.security.rbac import Permission
from schemas.leads.models import LeadStatus, NormalizedLead
from tools.analytics.lead_scoring import score_lead
from tools.base import BaseTool, ToolCallContext, ToolSpec


class LeadScoringTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="analytics.score_lead",
        description="Compute an explainable rules-based lead score",
        category=ActionCategory.READ,
        permission=Permission.LEADS_READ,
    )

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        lead = NormalizedLead.model_validate(payload["lead"])
        return score_lead(lead).model_dump(mode="json")


class SalesAnalyticsTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="analytics.sales_summary",
        description="Aggregate lead source, status and conversion metrics",
        category=ActionCategory.READ,
        permission=Permission.ANALYTICS_READ,
    )

    async def execute_with_context(
        self, payload: dict[str, Any], ctx: ToolCallContext
    ) -> dict[str, Any]:
        if ctx.principal.tenant_id != ctx.tenant_id:
            raise AuthorizationError("Principal belongs to a different organization")
        leads = [NormalizedLead.model_validate(item) for item in payload.get("leads", [])]
        if any(lead.tenant_id != ctx.tenant_id for lead in leads):
            raise AuthorizationError("Analytics leads belong to a different organization")
        return self._summarize(leads)

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Standalone aggregation only processes supplied data; it reads no runtime history.
        return self._summarize(
            [NormalizedLead.model_validate(item) for item in payload.get("leads", [])]
        )

    @staticmethod
    def _summarize(leads: list[NormalizedLead]) -> dict[str, Any]:
        total = len(leads)
        by_source = Counter(lead.source.value for lead in leads)
        by_status = Counter(lead.status.value for lead in leads)
        converted = by_status.get(LeadStatus.CONVERTED.value, 0)
        return {
            "total_leads": total,
            "by_source": dict(by_source),
            "by_status": dict(by_status),
            "conversion_rate": round(converted / total, 4) if total else 0.0,
        }
