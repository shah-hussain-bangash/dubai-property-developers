"""Authenticated source management and supplied-source-only answers for each agent."""

import asyncio
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.api.app.dependencies.auth import require_permission
from apps.api.app.dependencies.runtime import get_runtime
from core.exceptions.errors import DomainValidationError
from core.security.rbac import Permission, Principal
from knowledge.assigned_sources import AssignedSources
from knowledge.evaluation.supplied_sources import EvaluationSet, evaluate_sources
from knowledge.ingestion.assigned_inputs import MAX_IMPORT_BYTES, extract_input, import_website
from workflows.runtime import PlatformRuntime


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, private"


router = APIRouter(
    prefix="/knowledge/agents", tags=["agent-knowledge"], dependencies=[Depends(private_response)]
)


class SourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["text", "website"]
    text: str | None = Field(default=None, max_length=200_000)
    url: str | None = Field(default=None, max_length=2048)
    review_by: date | None = None
    customer_safe: bool = False


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=3, max_length=1000)


@router.post("/{agent}/evaluate")
async def evaluate_agent_sources(
    agent: str,
    request: Request,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.KNOWLEDGE_READ)),
) -> dict[str, Any]:
    store = source_store(runtime, agent)
    try:
        checks = EvaluationSet.model_validate_json(await bounded_body(request))
    except ValidationError:
        raise DomainValidationError(
            "Check the question set: use 1-20 unique, valid questions."
        ) from None
    if checks.agent_id != agent:
        raise DomainValidationError("Choose a question set saved for this agent.")
    return await asyncio.to_thread(evaluate_sources, store, principal.tenant_id, agent, checks)


def source_store(runtime: PlatformRuntime, agent: str) -> AssignedSources:
    runtime.agents.get(agent)
    if runtime.assigned_sources is None:
        raise HTTPException(
            503,
            "Knowledge storage is not enabled. Ask the workspace administrator to configure it.",
        )
    return runtime.assigned_sources


async def bounded_body(request: Request) -> bytes:
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_IMPORT_BYTES:
            raise HTTPException(413, "Files and source requests must be smaller than 2 MB.")
    return bytes(content)


@router.get("")
async def agent_sources_index(
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.KNOWLEDGE_READ)),
) -> dict[str, Any]:
    return {
        "configured": runtime.assigned_sources is not None,
        "agents": [
            {
                "id": a,
                "name": runtime.agents.get(a).spec.name,
                "status": runtime.agents.get(a).spec.implementation_status.value,
            }
            for a in runtime.agents.ids()
        ],
    }


@router.get("/{agent}/sources")
async def list_sources(
    agent: str,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.KNOWLEDGE_READ)),
) -> dict[str, Any]:
    store = source_store(runtime, agent)
    return {
        "agent_id": agent,
        "sources": await asyncio.to_thread(store.list_sources, principal.tenant_id, agent),
    }


@router.get("/{agent}/sources/{source_id}")
async def read_source(
    agent: str,
    source_id: str,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.KNOWLEDGE_READ)),
) -> dict[str, Any]:
    store = source_store(runtime, agent)
    saved = await asyncio.to_thread(store.read_source, principal.tenant_id, agent, source_id)
    return {"agent_id": agent, **saved}


@router.post("/{agent}/sources")
async def add_source(
    agent: str,
    request: Request,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.WORKFLOWS_EXECUTE)),
) -> dict[str, Any]:
    store = source_store(runtime, agent)
    data = await bounded_body(request)
    mime = request.headers.get("content-type", "").split(";")[0].lower().strip()
    review_by = None
    kind: str
    uri = None
    customer_safe = False
    if mime == "application/json":
        try:
            body = SourceInput.model_validate_json(data)
        except ValidationError:
            raise DomainValidationError("Check the source title, text or website link.") from None
        title, kind, review_by = body.title, body.kind, body.review_by
        customer_safe = body.customer_safe
        if kind == "website":
            if not body.url or body.text is not None:
                raise DomainValidationError("Provide one public website URL for this source.")
            pages, uri = await asyncio.to_thread(import_website, body.url)
        else:
            if not body.text or body.url is not None:
                raise DomainValidationError("Provide text for this source.")
            pages = [body.text]
    else:
        title = request.query_params.get("title", "Uploaded source")
        customer_safe = request.query_params.get("customer_safe") == "true"
        raw_review = request.query_params.get("review_by")
        if raw_review:
            try:
                review_by = date.fromisoformat(raw_review)
                if review_by.isoformat() != raw_review:
                    raise ValueError("Use a complete ISO calendar date.")
            except ValueError:
                raise DomainValidationError(
                    "Choose a valid review date in YYYY-MM-DD format."
                ) from None
        kind = {"application/pdf": "pdf", "text/plain": "text", "text/markdown": "markdown"}.get(
            mime, ""
        )
        if not kind:
            raise HTTPException(415, "Upload a PDF, text or Markdown file.")
        pages = await asyncio.to_thread(extract_input, data, mime)
    saved = await asyncio.to_thread(
        store.add, principal.tenant_id, agent, title, kind, pages, uri, review_by, customer_safe
    )
    return {"agent_id": agent, "source": saved}


@router.delete("/{agent}/sources/{source_id}")
async def remove_source(
    agent: str,
    source_id: str,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.WORKFLOWS_EXECUTE)),
) -> dict[str, bool]:
    store = source_store(runtime, agent)
    await asyncio.to_thread(store.remove, principal.tenant_id, agent, source_id)
    return {"removed": True}


@router.post("/{agent}/answer")
async def answer_from_sources(
    agent: str,
    body: Question,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.KNOWLEDGE_READ)),
) -> dict[str, Any]:
    store = source_store(runtime, agent)
    return await asyncio.to_thread(store.answer, principal.tenant_id, agent, body.question)
