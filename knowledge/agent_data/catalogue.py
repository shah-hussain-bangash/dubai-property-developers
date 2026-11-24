"""Agent-owned demo data, not model training or customer records.

Evaluation examples are never ingested into the knowledge store. Dataset IDs
are filenames selected by application code, not paths supplied by a visitor.
"""

from __future__ import annotations

import re
from datetime import date
from importlib.resources import files
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from knowledge.documents.models import AccessLevel, SourceDocument
from schemas.agents.models import AgentRunStatus


class KnowledgeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=20_000)
    access_level: AccessLevel = AccessLevel.PUBLIC
    allowed_roles: list[str] = Field(default_factory=list)
    review_by: date | None = None


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")
    input: dict[str, Any]
    expected_status: AgentRunStatus
    expected_output: dict[str, Any] = Field(default_factory=dict)
    expected_error: str | None = None


class AgentDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    version: Literal[1] = 1
    fictional: Literal[True] = True
    knowledge: list[KnowledgeEntry] = Field(min_length=1)
    evaluations: list[EvaluationCase] = Field(min_length=3)

    @model_validator(mode="after")
    def unique_entries(self) -> AgentDataset:
        if len({d.key for d in self.knowledge}) != len(self.knowledge):
            raise ValueError("knowledge keys must be unique within an agent dataset")
        if len({c.case_id for c in self.evaluations}) != len(self.evaluations):
            raise ValueError("evaluation case IDs must be unique within an agent dataset")
        return self

    def documents(self, tenant_id: str) -> list[SourceDocument]:
        return [
            SourceDocument(
                tenant_id=tenant_id,
                document_key=f"agent-{self.agent_id}-{entry.key}",
                title=entry.title,
                text=entry.text,
                access_level=entry.access_level,
                allowed_roles=entry.allowed_roles,
                review_by=entry.review_by,
                metadata={"agent_id": self.agent_id, "dataset_version": str(self.version)},
            )
            for entry in self.knowledge
        ]


def dataset_ids() -> list[str]:
    return sorted(
        entry.name.removesuffix(".json")
        for entry in files("knowledge.agent_data").joinpath("data").iterdir()
        if entry.name.endswith(".json")
    )


def load_agent_dataset(agent_id: str) -> AgentDataset:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", agent_id):
        raise ValueError("invalid agent dataset ID")
    resource = files("knowledge.agent_data").joinpath("data", f"{agent_id}.json")
    dataset = AgentDataset.model_validate_json(resource.read_text(encoding="utf-8"))
    if dataset.agent_id != agent_id:
        raise ValueError("dataset owner does not match its filename")
    return dataset


def agent_documents(tenant_id: str) -> list[SourceDocument]:
    return [
        doc for agent in dataset_ids() for doc in load_agent_dataset(agent).documents(tenant_id)
    ]
