"""Local fictional-property recommendation demo, using the existing workflow."""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from agents.base.context import ExecutionContext
from agents.property_recommendation.schemas import RecommendationOutput
from apps.api.app.api.v1.routes.leads import _require_isolated_demo
from apps.api.app.dependencies.auth import require_permission
from apps.api.app.dependencies.runtime import get_runtime
from core.observability.context import get_correlation_id, new_correlation_id
from core.security.rbac import Permission, Principal
from schemas.properties.models import PropertySearchCriteria
from workflows.property_flow import PROPERTY_RECOMMENDATION, PropertyFlowState
from workflows.runtime import PlatformRuntime

router = APIRouter(prefix="/properties", tags=["development-only"])


class DemoPropertyCriteria(PropertySearchCriteria):
    budget_max_aed: Decimal = Field(default=Decimal("2000000"), gt=0, le=10000000000)
    limit: int = Field(default=3, ge=1, le=5)


@router.post("/demo-recommendations", summary="[DEV ONLY] Match fictional properties")
async def demo_recommendations(
    criteria: DemoPropertyCriteria,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.WORKFLOWS_EXECUTE)),
) -> dict[str, Any]:
    _require_isolated_demo(runtime)
    context = ExecutionContext(
        principal=principal,
        tenant_id=principal.tenant_id,
        correlation_id=get_correlation_id() or new_correlation_id(),
    )
    run, state = await runtime.runner.run(
        PROPERTY_RECOMMENDATION, PropertyFlowState(criteria=criteria), context
    )
    if run.status != "succeeded" or not isinstance(state.output, RecommendationOutput):
        raise HTTPException(status_code=503, detail="Demo recommendation unavailable")
    if any(
        not item.listing.is_demo or item.listing.source != "demo-seed"
        for item in state.output.recommendations
    ):
        raise HTTPException(status_code=503, detail="Demo catalog response unavailable")
    return {
        "dev_only": True,
        "uses_mock_integrations": True,
        "status": "succeeded",
        "output": state.output.model_dump(mode="json"),
    }
