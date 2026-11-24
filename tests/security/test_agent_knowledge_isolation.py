"""Knowledge scope comes from authenticated tool context, not agent payloads."""

import pytest

from agents.base.context import ExecutionContext
from core.exceptions.errors import AuthorizationError, ToolPermissionError
from knowledge.agent_data.catalogue import dataset_ids
from knowledge.documents.models import AccessLevel, SourceDocument
from knowledge.vectorstores.base import RetrievalFilter
from workflows.runtime import PlatformRuntime


async def add_probe(runtime: PlatformRuntime, tenant: str, agent: str | None) -> None:
    await runtime.ingestion.ingest(
        SourceDocument(
            tenant_id=tenant,
            document_key=f"scopeprobe-{agent or 'general'}",
            title=f"Probe for {agent or 'general'}",
            text=f"scopeprobe sentinel belongs to {agent or 'general'} exclusively",
            access_level=AccessLevel.PUBLIC,
            metadata={"agent_id": agent} if agent else {},
        )
    )


@pytest.mark.parametrize("agent", dataset_ids())
async def test_all_agent_knowledge_scopes_are_independent(
    agent: str, runtime: PlatformRuntime, ctx: ExecutionContext
) -> None:
    for owner in dataset_ids():
        await add_probe(runtime, ctx.tenant_id, owner)
    await add_probe(runtime, ctx.tenant_id, None)
    await add_probe(runtime, "other-tenant", agent)
    result = await runtime.retriever.retrieve(
        "scopeprobe sentinel", RetrievalFilter(tenant_id=ctx.tenant_id, agent_id=agent), k=50
    )
    assert [hit.chunk.title for hit in result.hits] == [f"Probe for {agent}"]


@pytest.mark.parametrize(
    "agent", ["documents", "sales_conversation", "marketing", "email", "whatsapp"]
)
async def test_payload_cannot_select_another_agent_or_general_corpus(
    agent: str, runtime: PlatformRuntime, ctx: ExecutionContext
) -> None:
    other = "sales_conversation" if agent == "documents" else "documents"
    for owner in [agent, other, None]:
        await add_probe(runtime, ctx.tenant_id, owner)
    result = await runtime.agents.get(agent).use_tool(
        ctx,
        "documents.search",
        {
            "query": "scopeprobe sentinel",
            "tenant_id": ctx.tenant_id,
            "agent_id": other,
            "metadata_equals": {},
            "audience": "customer",
            "k": 50,
        },
    )
    assert [c["title"] for c in result.data["citations"]] == [f"Probe for {agent}"]


async def test_contextual_search_rejects_other_tenant(
    runtime: PlatformRuntime, ctx: ExecutionContext
) -> None:
    with pytest.raises(AuthorizationError):
        await runtime.agents.get("documents").use_tool(
            ctx, "documents.search", {"query": "payment plan", "tenant_id": "other-tenant"}
        )


async def test_unscoped_search_cannot_read_agent_owned_documents(
    runtime: PlatformRuntime, ctx: ExecutionContext
) -> None:
    await add_probe(runtime, ctx.tenant_id, "documents")
    result = await runtime.tools.get("documents.search").execute(
        {"query": "scopeprobe sentinel", "tenant_id": ctx.tenant_id, "agent_id": "documents"}
    )
    assert result["citations"] == []


async def test_payload_roles_cannot_widen_restricted_access(
    runtime: PlatformRuntime, ctx: ExecutionContext
) -> None:
    await runtime.ingestion.ingest(
        SourceDocument(
            tenant_id=ctx.tenant_id,
            document_key="restricted-scopeprobe",
            title="Restricted sentinel",
            text="scopeprobe sentinel restricted private document",
            access_level=AccessLevel.RESTRICTED,
            allowed_roles=["admin"],
            metadata={"agent_id": "documents"},
        )
    )
    result = await runtime.agents.get("documents").use_tool(
        ctx,
        "documents.search",
        {
            "query": "scopeprobe sentinel",
            "tenant_id": ctx.tenant_id,
            "audience": "staff",
            "roles": ["admin"],
        },
    )
    assert result.data["citations"] == []


async def test_scoping_does_not_grant_extra_tools(
    runtime: PlatformRuntime, ctx: ExecutionContext
) -> None:
    with pytest.raises(ToolPermissionError):
        await runtime.agents.get("qualification").use_tool(
            ctx, "documents.search", {"query": "anything", "tenant_id": ctx.tenant_id}
        )
