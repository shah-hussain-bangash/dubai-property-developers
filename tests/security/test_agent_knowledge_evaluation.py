"""Evaluation examples remain separate from knowledge, tenant and agent scopes."""

import pytest

from knowledge.agent_data.catalogue import dataset_ids
from tests.security.test_assigned_source_api_isolation import BASE, add, headers, workspace


def checks(agent, excerpt="eight gardens"):
    return {
        "agent_id": agent,
        "cases": [
            {
                "id": "known",
                "question": "project gardens",
                "expectation": "answer",
                "expected_excerpt": excerpt,
            },
            {"id": "missing", "question": "quasar telescope", "expectation": "no_answer"},
        ],
    }


@pytest.mark.parametrize("agent", dataset_ids())
def test_every_agent_evaluates_only_own_sources_without_saving_examples(tmp_path, agent):
    with workspace(tmp_path / "checks.sqlite3") as client:
        own = add(client, agent, "Fictional project contains eight gardens.")
        add(client, agent, "Fictional project contains nine gardens.", "b-manager")
        other = next(a for a in dataset_ids() if a != agent)
        add(client, other, "Fictional quasar telescope belongs to another agent.")
        route = f"{BASE}/{agent}"
        before = client.get(route + "/sources", headers=headers()).json()
        response = client.post(route + "/evaluate", json=checks(agent), headers=headers("a-viewer"))
        assert response.status_code == 200, response.text
        assert "no-store" in response.headers["cache-control"]
        report = response.json()
        assert (report["evaluated"], report["passed"], report["failed"]) == (2, 2, 0)
        assert report["agent_id"] == agent and report["sent"] is False
        assert report["supplied_sources_only"] is True
        assert report["cases"][0]["answer"]["sources"][0]["source_id"] == own
        assert report["cases"][1]["answer"]["answered"] is False
        foreign = client.post(route + "/evaluate", json=checks(agent), headers=headers("b-manager"))
        assert foreign.json()["passed"] == 1
        # Expected text cannot supply a missing fact, either now or on a later question.
        poisoned = checks(agent, "quasar telescope")
        poisoned["cases"][0]["question"] = "quasar telescope"
        result = client.post(route + "/evaluate", json=poisoned, headers=headers()).json()
        assert result["cases"][0]["passed"] is False
        assert result["cases"][0]["answer"]["answered"] is False
        assert client.get(route + "/sources", headers=headers()).json() == before
        add(client, agent, "Fictional quasar telescope is now supplied.")
        rerun = client.post(route + "/evaluate", json=checks(agent), headers=headers()).json()
        assert rerun["cases"][1]["passed"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: s.update(agent_id="marketing"),
        lambda s: s.update(cases=[]),
        lambda s: s.update(cases=s["cases"] * 11),
        lambda s: s["cases"][1].update(id="known"),
        lambda s: s["cases"][0].update(question="  "),
        lambda s: s["cases"][0].update(question="x" * 1001),
        lambda s: s["cases"][0].update(expected_excerpt=None),
        lambda s: s["cases"][0].update(expected_excerpt="  "),
        lambda s: s["cases"][0].update(expected_excerpt="x" * 1001),
        lambda s: s["cases"][1].update(expected_excerpt="forbidden"),
        lambda s: s["cases"][1].update(expectation="invent"),
        lambda s: s["cases"][0].update(id="../bad"),
        lambda s: s.update(tenant_id="tenant-b"),
        lambda s: s["cases"][0].update(sources=["injected"]),
    ],
)
def test_invalid_sets_are_rejected_without_source_writes(tmp_path, mutation):
    with workspace(tmp_path / "checks.sqlite3") as client:
        data = checks("documents")
        mutation(data)
        response = client.post(f"{BASE}/documents/evaluate", json=data, headers=headers())
        assert response.status_code == 422, response.text
        assert client.get(f"{BASE}/documents/sources", headers=headers()).json()["sources"] == []


def test_evaluation_requires_auth_and_bounds_body(tmp_path):
    with workspace(tmp_path / "checks.sqlite3") as client:
        route = f"{BASE}/documents/evaluate"
        assert client.post(route, json=checks("documents")).status_code == 401
        assert client.post(route, content=b"invalid", headers=headers()).status_code == 422
        assert client.post(route, content=b"x" * 2_000_001, headers=headers()).status_code == 413
        assert (
            client.post(
                f"{BASE}/unknown/evaluate", json=checks("unknown"), headers=headers()
            ).status_code
            == 404
        )


def test_expected_passage_must_be_in_excerpt_not_source_title(tmp_path):
    with workspace(tmp_path / "checks.sqlite3") as client:
        add(client, "documents", "Fictional project contains eight gardens.")
        report = client.post(
            f"{BASE}/documents/evaluate",
            json=checks("documents", "Fictional boundary fixture"),
            headers=headers(),
        ).json()
        assert report["cases"][0]["answer"]["answered"] is True
        assert report["cases"][0]["passed"] is False
