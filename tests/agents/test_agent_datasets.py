"""Run each agent against its own fictional, held-out evaluation inputs."""

from typing import Any

import pytest

from agents.base.context import ExecutionContext
from agents.registry import AGENT_CLASSES
from knowledge.agent_data.catalogue import AgentDataset, dataset_ids, load_agent_dataset
from workflows.runtime import PlatformRuntime

CASES = [(agent, case) for agent in dataset_ids() for case in load_agent_dataset(agent).evaluations]


def test_every_registered_agent_has_a_separate_dataset() -> None:
    assert set(dataset_ids()) == {agent.spec.agent_id for agent in AGENT_CLASSES}
    assert len(dataset_ids()) == 13
    for agent in dataset_ids():
        dataset = load_agent_dataset(agent)
        assert dataset.agent_id == agent and dataset.fictional
        assert len(dataset.evaluations) >= 3
        assert len({case.expected_status for case in dataset.evaluations}) >= 2
        documents = dataset.documents("fictional-tenant")
        assert all(doc.metadata["agent_id"] == agent for doc in documents)
        # Held-out examples are not part of the material ingested for retrieval.
        assert all("expected_output" not in doc.metadata for doc in documents)


@pytest.mark.parametrize("agent,case", CASES, ids=[f"{a}/{c.case_id}" for a, c in CASES])
async def test_agent_held_out_cases(
    agent: str, case: Any, runtime: PlatformRuntime, ctx: ExecutionContext
) -> None:
    result = await runtime.agents.get(agent).run(case.input, ctx)
    assert result.status == case.expected_status, result.model_dump()
    if case.expected_error:
        assert result.error and result.error.code == case.expected_error
    if case.expected_output:
        assert result.output is not None
        output = result.output.model_dump(mode="json")
        for path, expected in case.expected_output.items():
            actual = output
            for segment in path.split("."):
                actual = actual[int(segment)] if isinstance(actual, list) else actual[segment]
            assert actual == expected, (path, actual, expected)
    assert runtime.email_sender.outbox == []


def test_registry_returns_detached_agent_data(runtime: PlatformRuntime) -> None:
    dataset = runtime.agents.dataset("documents")
    dataset.knowledge.clear()
    dataset.evaluations[0].input.clear()
    assert runtime.agents.dataset("documents").knowledge
    assert runtime.agents.dataset("documents").evaluations[0].input


@pytest.mark.parametrize("invalid", ["../documents", "/documents", "documents.json", ""])
def test_dataset_ids_are_not_arbitrary_paths(invalid: str) -> None:
    with pytest.raises(ValueError):
        load_agent_dataset(invalid)


def test_dataset_rejects_duplicate_example_ids() -> None:
    data = load_agent_dataset("supervisor").model_dump()
    data["evaluations"][1]["case_id"] = data["evaluations"][0]["case_id"]
    with pytest.raises(ValueError, match="evaluation case IDs"):
        AgentDataset.model_validate(data)


def test_dataset_preserves_source_review_dates() -> None:
    for agent in ["sales_conversation", "documents"]:
        documents = load_agent_dataset(agent).documents("fictional-tenant")
        assert all(
            doc.review_by is not None for doc in documents if "payment-plan" in doc.document_key
        )
