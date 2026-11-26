"""Read-only checks against one agent's currently supplied sources."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from knowledge.assigned_sources import AssignedSources


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    question: str = Field(min_length=3, max_length=1000)
    expectation: Literal["answer", "no_answer"]
    expected_excerpt: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def check_expectation(self) -> "EvaluationCase":
        if (self.expectation == "answer") != (self.expected_excerpt is not None):
            raise ValueError("Provide an expected passage only for an answer check.")
        return self


class EvaluationSet(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    agent_id: str = Field(min_length=1, max_length=100)
    cases: list[EvaluationCase] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_ids(self) -> "EvaluationSet":
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Question IDs must be unique.")
        return self


def evaluate_sources(
    store: AssignedSources, tenant: str, agent: str, checks: EvaluationSet
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case in checks.cases:
        # Expected passages never enter retrieval or the source store.
        answer = store.answer(tenant, agent, case.question)
        passed = (
            not answer["answered"]
            if case.expectation == "no_answer"
            else any(case.expected_excerpt in source["excerpt"] for source in answer["sources"])
        )
        results.append({"id": case.id, "passed": passed, "answer": answer})
    passed_count = sum(result["passed"] for result in results)
    return {
        "agent_id": agent,
        "supplied_sources_only": True,
        "sent": False,
        "evaluated": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "cases": results,
    }
