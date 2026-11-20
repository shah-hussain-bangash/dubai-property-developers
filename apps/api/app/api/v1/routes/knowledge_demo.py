"""Cited, public-only knowledge demo using the existing support workflow."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, StringConstraints

from agents.base.context import ExecutionContext
from apps.api.app.api.v1.routes.leads import _require_isolated_demo
from apps.api.app.dependencies.auth import require_permission
from apps.api.app.dependencies.runtime import get_runtime
from core.observability.context import get_correlation_id, new_correlation_id
from core.security.rbac import Permission, Principal
from knowledge.documents.demo_corpus import demo_documents
from knowledge.documents.models import AccessLevel
from workflows.customer_support_flow import KNOWLEDGE_SUPPORT, SupportFlowState
from workflows.runtime import PlatformRuntime

router = APIRouter(prefix="/knowledge", tags=["development-only"])


class DemoKnowledgeQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)
    ]


@router.post("/demo-answer", summary="[DEV ONLY] Ask public fictional documents")
async def demo_answer(
    body: DemoKnowledgeQuestion,
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
        KNOWLEDGE_SUPPORT, SupportFlowState(question=body.question, audience="customer"), context
    )
    if run.status not in {"pending_approval", "escalated"} or state.answer is None:
        raise HTTPException(status_code=503, detail="Demo knowledge answer unavailable")
    allowed = {
        doc.document_id
        for doc in demo_documents(principal.tenant_id)
        if doc.access_level == AccessLevel.PUBLIC
    }
    if any(citation.document_id not in allowed for citation in state.answer.citations):
        raise HTTPException(status_code=503, detail="Demo public sources unavailable")
    if state.answer.answer and not state.answer.citations:
        raise HTTPException(status_code=503, detail="Demo cited answer unavailable")
    return {
        "dev_only": True,
        "uses_mock_integrations": True,
        "source": "fictional-demo-corpus",
        "status": run.status,
        "output": state.answer.model_dump(mode="json"),
    }
