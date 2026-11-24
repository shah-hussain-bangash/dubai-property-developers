from __future__ import annotations

import re
from collections import Counter
from typing import ClassVar

from agents.base.agent import AgentSpec, BaseAgent
from agents.base.context import ExecutionContext
from agents.documents.schemas import DocumentAction, DocumentAgentInput, DocumentAgentOutput
from core.exceptions.errors import DomainValidationError
from knowledge.embeddings.base import tokenize
from schemas.agents.models import AgentRunStatus, ImplementationStatus
from schemas.conversations.models import Citation

CONFIDENCE_THRESHOLD = 0.15


def extractive_summary(text: str, max_sentences: int) -> str:
    """Pick the highest term-frequency sentences, preserving original order."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) <= max_sentences:
        return " ".join(sentences)
    freq = Counter(tokenize(text))
    scored = [
        (sum(freq[t] for t in tokenize(s)) / (len(tokenize(s)) or 1), i)
        for i, s in enumerate(sentences)
    ]
    keep = sorted(i for _, i in sorted(scored, reverse=True)[:max_sentences])
    return " ".join(sentences[i] for i in keep)


class DocumentAgent(BaseAgent[DocumentAgentInput, DocumentAgentOutput]):
    spec: ClassVar[AgentSpec] = AgentSpec(
        agent_id="documents",
        name="Document Agent",
        description="Summarizes permitted documents and answers questions with citations (RAG).",
        responsibilities=[
            "Read permitted property documents",
            "Extract relevant information",
            "Prepare document summaries",
            "Support retrieval-augmented answers with citations",
        ],
        implementation_status=ImplementationStatus.PARTIAL,
        allowed_tools=frozenset({"documents.search"}),
        status_notes="Supplied-source summaries and answers use cited own passages; "
        "generative answers pending an LLM provider.",
    )
    input_model = DocumentAgentInput
    output_model = DocumentAgentOutput

    async def execute(self, data: DocumentAgentInput, ctx: ExecutionContext) -> DocumentAgentOutput:
        summarize = data.action == DocumentAction.SUMMARIZE
        if summarize and not self.deps.supplied_knowledge_only:
            if not data.text:
                raise DomainValidationError("text is required to summarize")
            return DocumentAgentOutput(summary=extractive_summary(data.text, data.max_sentences))

        if summarize and (not data.query or not data.query.strip()):
            return DocumentAgentOutput(
                needs_human=True,
                notes=["Provide a query to summarize this agent's assigned sources."],
            )

        if not data.query:
            raise DomainValidationError("query is required to answer")
        result = await self.use_tool(
            ctx,
            "documents.search",
            {
                "query": data.query,
                "tenant_id": ctx.tenant_id,
                "audience": data.audience,
                "roles": sorted(r.value for r in ctx.principal.roles),
                "k": 3,
            },
        )
        confidence = float(result.data.get("top_score", 0.0))
        citations = [Citation.model_validate(c) for c in result.data.get("citations", [])]
        notes: list[str] = []
        if result.data.get("has_stale"):
            notes.append("Some sources are past their review date; verify before relying on them.")
        if (
            confidence < CONFIDENCE_THRESHOLD
            or not result.data.get("passages")
            or (self.deps.supplied_knowledge_only and not citations)
        ):
            return DocumentAgentOutput(
                confidence=confidence,
                needs_human=True,
                notes=[*notes, "No sufficiently relevant authorized document found."],
            )
        return DocumentAgentOutput(
            summary=extractive_summary(
                "\n\n".join(c.excerpt for c in citations), data.max_sentences
            )
            if summarize
            else None,
            answer=None if summarize else result.data["passages"][0],
            citations=citations,
            confidence=confidence,
            needs_human=bool(result.data.get("has_stale")),
            notes=notes,
        )

    def outcome_status(self, output: DocumentAgentOutput) -> AgentRunStatus:
        return AgentRunStatus.ESCALATED if output.needs_human else AgentRunStatus.SUCCEEDED
