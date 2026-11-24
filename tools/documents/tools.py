from __future__ import annotations

from typing import Any, ClassVar

from core.exceptions.errors import AuthorizationError
from core.policies.actions import ActionCategory
from core.security.rbac import Permission
from knowledge.assigned_sources import AssignedSources
from knowledge.documents.models import AccessLevel
from knowledge.retrieval.retriever import Retriever
from knowledge.vectorstores.base import RetrievalFilter
from tools.base import BaseTool, ToolCallContext, ToolSpec


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

    def __init__(
        self, retriever: Retriever, assigned_sources: AssignedSources | None = None
    ) -> None:
        self._retriever = retriever
        self._assigned_sources = assigned_sources

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._assigned_sources is not None:
            raise AuthorizationError("Supplied knowledge requires a trusted agent identity")
        # Direct internal searches retain access to general documents only.
        return await self._search(payload, None)

    async def execute_with_context(
        self, payload: dict[str, Any], ctx: ToolCallContext
    ) -> dict[str, Any]:
        if payload.get("tenant_id") != ctx.tenant_id:
            raise AuthorizationError("knowledge search belongs to a different organization")
        if self._assigned_sources is not None:
            if not ctx.agent_id:
                raise AuthorizationError("Select an agent for supplied knowledge")
            import asyncio

            return await asyncio.to_thread(
                self._assigned_sources.tool_search,
                ctx.tenant_id,
                ctx.agent_id,
                payload["query"],
                payload.get("audience", "customer") == "customer",
            )
        scoped = {**payload, "roles": sorted(role.value for role in ctx.principal.roles)}
        return await self._search(scoped, ctx.agent_id)

    async def _search(self, payload: dict[str, Any], agent_id: str | None) -> dict[str, Any]:
        audience = payload.get("audience", "customer")
        levels = (
            {AccessLevel.PUBLIC}
            if audience == "customer"
            else {AccessLevel.PUBLIC, AccessLevel.INTERNAL, AccessLevel.RESTRICTED}
        )
        filters = RetrievalFilter(
            tenant_id=payload["tenant_id"],
            agent_id=agent_id,
            access_levels=levels,
            principal_roles=set(payload.get("roles", [])),
        )
        result = await self._retriever.retrieve(
            payload["query"], filters, k=int(payload.get("k", 4))
        )
        return {
            "top_score": result.top_score,
            "has_stale": result.has_stale,
            "citations": [c.model_dump() for c in result.citations()],
            "passages": [h.chunk.content for h in result.hits],
        }
