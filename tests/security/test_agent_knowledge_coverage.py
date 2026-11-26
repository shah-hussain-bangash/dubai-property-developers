"""Source coverage is read-only, current and organization scoped."""

from datetime import date, timedelta
from unittest.mock import patch

from knowledge.agent_data.catalogue import dataset_ids
from knowledge.assigned_sources import AssignedSources
from tests.security.test_assigned_source_api_isolation import BASE, headers, workspace


def test_all_agents_coverage_deadlines_approval_and_restart(tmp_path):
    today = date(2030, 1, 3)

    class Day(date):
        @classmethod
        def today(cls):
            return today

    path = tmp_path / "sources.sqlite3"
    store = AssignedSources(str(path))
    agents = list(dataset_ids())
    with patch("knowledge.assigned_sources.date", Day):
        # Import dated fixtures while valid, then use the selected test day.
        for agent in agents:
            for n, deadline, approved in [
                (1, None, False),
                (2, today, True),
                (3, today + timedelta(days=7), True),
                (4, today + timedelta(days=8), False),
            ]:
                store.add(
                    "tenant-a",
                    agent,
                    f"Fictional {n}",
                    "text",
                    [f"Fictional policy {n}."],
                    review_by=deadline,
                    customer_safe=approved,
                )
            store.add(
                "tenant-b",
                agent,
                "Foreign policy",
                "text",
                ["Fictional foreign secretmarker."],
                customer_safe=True,
            )

        class Past(date):
            @classmethod
            def today(cls):
                return today - timedelta(days=1)

        with patch("knowledge.assigned_sources.date", Past):
            for agent in agents:
                store.add(
                    "tenant-a",
                    agent,
                    "Expired policy",
                    "text",
                    ["Fictional expired policy."],
                    review_by=Past.today(),
                    customer_safe=True,
                )
        store.add(
            "tenant-a",
            "unregistered",
            "Legacy source",
            "text",
            ["Fictional unregistered secretmarker."],
        )
        before = {agent: store.list_sources("tenant-a", agent) for agent in agents}
        with workspace(path) as client:
            response = client.get(BASE + "/coverage", headers=headers("a-viewer"))
            assert response.status_code == 200, response.text
            assert "no-store" in response.headers["cache-control"]
            result = response.json()
            assert result["as_of"] == "2030-01-03" and result["window_days"] == 7
            assert {r["agent_id"] for r in result["agents"]} == set(agents)
            for row in result["agents"]:
                assert row == {
                    "agent_id": row["agent_id"],
                    "total": 5,
                    "staff_eligible": 4,
                    "customer_eligible": 2,
                    "overdue": 1,
                    "due_soon": 2,
                    "undated": 1,
                }
            assert result["summary"] == {
                "total": 65,
                "staff_eligible": 52,
                "customer_eligible": 26,
                "overdue": 13,
                "due_soon": 26,
                "undated": 13,
            }
            assert (
                "secretmarker" not in response.text
                and "title" not in response.text
                and "pages" not in response.text
            )
            foreign = client.get(
                BASE + "/coverage?tenant=tenant-a", headers=headers("b-manager")
            ).json()
            assert (
                foreign["summary"]["total"] == 13 and foreign["summary"]["customer_eligible"] == 13
            )
        assert all(store.list_sources("tenant-a", agent) == before[agent] for agent in agents)
        with workspace(path) as client:
            assert client.get(BASE + "/coverage", headers=headers()).json() == result
            agent = agents[0]
            source = next(s for s in before[agent] if s["title"] == "Expired policy")
            assert (
                client.patch(
                    f"{BASE}/{agent}/sources/{source['id']}/review",
                    headers=headers(),
                    json={"reviewed": True, "review_by": "2030-01-05", "customer_safe": True},
                ).status_code
                == 200
            )
            renewed = client.get(BASE + "/coverage", headers=headers()).json()
            assert (
                renewed["summary"]["overdue"] == 12
                and renewed["summary"]["customer_eligible"] == 27
            )
            assert (
                client.delete(
                    f"{BASE}/{agent}/sources/{source['id']}", headers=headers()
                ).status_code
                == 200
            )
            assert (
                client.get(BASE + "/coverage", headers=headers()).json()["summary"]["total"] == 64
            )
        for agent in agents[1:]:
            assert store.list_sources("tenant-a", agent) == before[agent]
            for source in before[agent]:
                assert store.review_history("tenant-a", agent, source["id"])["events"] == []


def test_empty_coverage_and_auth(tmp_path):
    with workspace(tmp_path / "sources.sqlite3") as client:
        assert client.get(BASE + "/coverage").status_code == 401
        result = client.get(BASE + "/coverage", headers=headers()).json()
        assert len(result["agents"]) == 13 and all(r["total"] == 0 for r in result["agents"])
        assert all(value == 0 for value in result["summary"].values())


def test_registry_filter_and_empty_registry(tmp_path):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    store.add("tenant-a", "documents", "Fixture", "text", ["Fictional fixture."])
    assert store.coverage("tenant-a", [])["agents"] == []
    assert store.coverage("tenant-a", ["marketing"])["summary"]["total"] == 0
