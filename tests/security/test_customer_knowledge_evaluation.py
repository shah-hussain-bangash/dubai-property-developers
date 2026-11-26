"""Repeatable customer checks preserve approval and ownership boundaries."""

from datetime import date, timedelta

import pytest

from knowledge.agent_data.catalogue import dataset_ids
from tests.security.test_assigned_source_api_isolation import BASE, headers, workspace


def question_set(agent, audience="customer"):
    return {
        "agent_id": agent,
        "audience": audience,
        "cases": [
            {
                "id": "approved",
                "question": "publicmarker gardens",
                "expectation": "answer",
                "expected_excerpt": "two visits",
            },
            {"id": "staff", "question": "internalmarker balcony", "expectation": "no_answer"},
            {"id": "expired", "question": "expiredmarker parking", "expectation": "no_answer"},
            {"id": "foreign", "question": "foreignmarker astronomy", "expectation": "no_answer"},
        ],
    }


@pytest.mark.parametrize("agent", dataset_ids())
def test_customer_checks_remain_scoped_read_only_and_follow_source_lifecycle(
    tmp_path, monkeypatch, agent
):
    today = date.today()
    path = tmp_path / "checks.sqlite3"
    route = f"{BASE}/{agent}"
    with workspace(path) as client:

        def add(target, text, approved, review=None, identity="a-manager"):
            response = client.post(
                f"{BASE}/{target}/sources",
                headers=headers(identity),
                json={
                    "title": "Fictional customer check",
                    "kind": "text",
                    "text": text,
                    "customer_safe": approved,
                    "review_by": review,
                },
            )
            assert response.status_code == 200, response.text
            return response.json()["source"]["id"]

        source_id = add(
            agent, "Fictional publicmarker gardens allow two visits.", True, today.isoformat()
        )
        add(agent, "Fictional internalmarker balcony contains staff details.", False)

        class Yesterday(date):
            @classmethod
            def today(cls):
                return today - timedelta(days=1)

        # Import while valid, then advance only the source store's test calendar.
        with monkeypatch.context() as clock:
            clock.setattr("knowledge.assigned_sources.date", Yesterday)
            add(
                agent,
                "Fictional expiredmarker parking contains old rules.",
                True,
                (today - timedelta(days=1)).isoformat(),
            )
        other = next(a for a in dataset_ids() if a != agent)
        add(other, "Fictional foreignmarker astronomy allows two visits.", True)
        add(
            agent,
            "Fictional foreignmarker astronomy allows two visits.",
            True,
            identity="b-manager",
        )
        before = client.get(route + "/sources", headers=headers()).json()
        checks = question_set(agent)

        def evaluate(body):
            response = client.post(route + "/evaluate", headers=headers("a-viewer"), json=body)
            assert response.status_code == 200, response.text
            assert "no-store" in response.headers["cache-control"]
            return response.json()

        report = evaluate(checks)
        assert report["audience"] == "customer" and report["sent"] is False
        assert (report["evaluated"], report["passed"], report["failed"]) == (4, 4, 0)
        assert all(r["answer"]["audience"] == "customer" for r in report["cases"])
        assert [s["source_id"] for s in report["cases"][0]["answer"]["sources"]] == [source_id]
        assert all(not r["answer"]["sources"] for r in report["cases"][1:])
        staff = question_set(agent, "staff")
        explicit_staff = evaluate(staff)
        del staff["audience"]
        assert evaluate(staff) == explicit_staff and "audience" not in explicit_staff
        assert explicit_staff["cases"][1]["passed"] is False
        assert client.get(route + "/sources", headers=headers()).json() == before
        assert (
            client.get(route + "/sources/" + source_id + "/reviews", headers=headers()).json()[
                "events"
            ]
            == []
        )
        # Expected answers never supply facts to retrieval.
        poisoned = question_set(agent)
        poisoned["cases"][0]["question"] = "missingmarker telescope"
        assert evaluate(poisoned)["cases"][0]["answer"]["answered"] is False
        withdrawn = client.patch(
            route + "/sources/" + source_id + "/review",
            headers=headers(),
            json={
                "reviewed": True,
                "review_by": (today + timedelta(days=2)).isoformat(),
            },
        )
        assert withdrawn.status_code == 200
        assert evaluate(checks)["cases"][0]["passed"] is False
        restored = client.patch(
            route + "/sources/" + source_id + "/review",
            headers=headers(),
            json={
                "reviewed": True,
                "customer_safe": True,
                "review_by": today.isoformat(),
            },
        )
        assert restored.status_code == 200
        assert evaluate(checks)["passed"] == 4

    class Tomorrow(date):
        @classmethod
        def today(cls):
            return today + timedelta(days=1)

    monkeypatch.setattr("knowledge.assigned_sources.date", Tomorrow)
    with workspace(path) as client:
        report = client.post(route + "/evaluate", headers=headers(), json=checks).json()
        assert report["audience"] == "customer" and report["passed"] == 3
        assert not report["cases"][0]["answer"]["answered"]
        assert not report["cases"][0]["passed"]
        client.delete(route + "/sources/" + source_id, headers=headers())
        report = client.post(route + "/evaluate", headers=headers(), json=checks).json()
        assert not report["cases"][0]["answer"]["sources"]


@pytest.mark.parametrize("audience", [None, True, "all", "Customer", "staff,customer", {}, []])
def test_invalid_customer_check_audiences_are_rejected(tmp_path, audience):
    with workspace(tmp_path / "checks.sqlite3") as client:
        checks = question_set("documents", audience)
        assert (
            client.post(f"{BASE}/documents/evaluate", headers=headers(), json=checks).status_code
            == 422
        )
