from __future__ import annotations

from typing import Any, ClassVar

from core.policies.actions import ActionCategory
from core.security.rbac import Permission
from knowledge.documents.models import AccessLevel
from knowledge.retrieval.retriever import Retriever
from knowledge.vectorstores.base import RetrievalFilter
from tools.base import BaseTool, ToolSpec


class DocumentSearchTool(BaseTool):
    """Payload: query, tenant_id, audience ("customer" | "staff"), roles, k.

    Customer-facing searches only ever see PUBLIC documents, regardless of the
    caller's own roles, so internal material cannot leak into customer replies.
    """

    spec: ClassVar[ToolSpec] = ToolSpec(
        name="documents.search",
        description="Permission-aware semantic search over authorized documents",
        category=ActionCategory.READ,
        permission=Permission.KNOWLEDGE_READ,
    )

    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        audience = payload.get("audience", "customer")
        levels = (
            {AccessLevel.PUBLIC}
            if audience == "customer"
            else {AccessLevel.PUBLIC, AccessLevel.INTERNAL, AccessLevel.RESTRICTED}
        )
        filters = RetrievalFilter(
            tenant_id=payload["tenant_id"],
            access_levels=levels,
            principal_roles=set(payload.get("roles", [])),
        )
        result = await self._retriever.retrieve(payload["query"], filters, k=int(payload.get("k", 4)))
        return {
            "top_score": result.top_score,
            "has_stale": result.has_stale,
            "citations": [c.model_dump() for c in result.citations()],
            "passages": [h.chunk.content for h in result.hits],
        }
