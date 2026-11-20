"""Unsent fictional web-chat drafts from the existing sales workflow."""

from typing import Annotated, Any
from uuid import uuid4

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
from workflows.runtime import PlatformRuntime
from workflows.sales_flow import SALES_CONVERSATION, SalesFlowState

router = APIRouter(prefix="/conversations", tags=["development-only"])


class DemoConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=4096)]


@router.post("/demo-draft", summary="[DEV ONLY] Prepare an unsent fictional reply")
async def demo_draft(
    body: DemoConversationMessage,
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
        SALES_CONVERSATION,
        SalesFlowState.model_validate(
            {
                "message": {
                    "conversation_id": "demo-draft-" + uuid4().hex,
                    "channel": "web_chat",
                    "direction": "inbound",
                    "sender": "fictional-customer",
                    "text": body.message,
                },
                "customer_first_name": "Demo",
            }
        ),
        context,
    )
    if (
        run.status not in {"pending_approval", "escalated"}
        or state.reply is None
        or state.whatsapp is not None
    ):
        raise HTTPException(status_code=503, detail="Demo reply unavailable")
    reply = state.reply
    if reply.draft.requires_approval is not True or reply.draft.is_template is not True:
        raise HTTPException(status_code=503, detail="Demo draft unavailable")
    allowed = {
        doc.document_id
        for doc in demo_documents(principal.tenant_id)
        if doc.access_level == AccessLevel.PUBLIC
    }
    if any(citation.document_id not in allowed for citation in reply.draft.citations):
        raise HTTPException(status_code=503, detail="Demo public sources unavailable")
    needs_human = run.status == "escalated"
    reason = None
    if needs_human:
        if reply.intent == "complaint":
            reason = "A complaint needs a staff member to handle it."
        elif reply.intent == "unsubscribe":
            reason = (
                "The customer asked to stop contact. Staff must review and record that request."
            )
        elif reply.injection_signals:
            reason = "The message contains instructions that need staff review."
        else:
            reason = "No current public demo document supports this reply. Ask a staff member to review it."
    return {
        "dev_only": True,
        "uses_mock_integrations": True,
        "source": "fictional-sales-demo",
        "status": run.status,
        "sent": False,
        "requires_approval": True,
        "channel": "web_chat",
        "needs_human": needs_human,
        "handoff_reason": reason,
        "intent": reply.intent,
        "language": reply.language,
        "draft": reply.draft.text,
        "citations": [citation.model_dump(mode="json") for citation in reply.draft.citations],
    }
