"""Read-only source review queues share retrieval's calendar and owner scope."""

from datetime import date, timedelta

import pytest

from knowledge.agent_data.catalogue import dataset_ids
from tests.security.test_assigned_source_api_isolation import BASE, headers, workspace


@pytest.mark.parametrize("agent", dataset_ids())
def test_each_agent_queue_uses_server_dates_and_excludes_foreign_sources(
    tmp_path, monkeypatch, agent
):
    class Clock(date):
        day = date(2030, 1, 2)

        @classmethod
        def today(cls):
            return cls.day

    monkeypatch.setattr("knowledge.assigned_sources.date", Clock)
    route = f"{BASE}/{agent}"
    path = tmp_path / "sources.sqlite3"
    offsets = [0, 1, 8, 9, None]
    with workspace(path) as client:
        ids = []
        for index, offset in enumerate(offsets):
            payload = {
                "kind": "text",
                "title": f"Fictional deadline {index}",
                "text": f"Fictional gardens marker{index}.",
                "customer_safe": index % 2 == 0,
            }
            if offset is not None:
                payload["review_by"] = (Clock.day + timedelta(days=offset)).isoformat()
            response = client.post(route + "/sources", headers=headers(), json=payload)
            assert response.status_code == 200, response.text
            ids.append(response.json()["source"]["id"])
        other = next(a for a in dataset_ids() if a != agent)
        for target, identity in [(agent, "b-manager"), (other, "a-manager")]:
            response = client.post(
                f"{BASE}/{target}/sources",
                headers=headers(identity),
                json={
                    "kind": "text",
                    "title": "Foreign fixture",
                    "text": "Fictional foreign gardens.",
                    "review_by": Clock.day.isoformat(),
                },
            )
            assert response.status_code == 200
    Clock.day = date(2030, 1, 3)
    with workspace(path) as client:
        before = client.get(route + "/sources", headers=headers()).json()
        response = client.get(route + "/review-queue", headers=headers("a-viewer"))
        assert response.status_code == 200 and "no-store" in response.headers["cache-control"]
        queue = response.json()
        assert (
            queue["agent_id"] == agent
            and queue["as_of"] == "2030-01-03"
            and queue["window_days"] == 7
        )
        assert queue["summary"] == {"overdue": 1, "due_soon": 2, "current": 1, "undated": 1}
        assert [item["id"] for item in queue["items"]] == ids[:3]
        assert [item["review_status"] for item in queue["items"]] == [
            "overdue",
            "due_soon",
            "due_soon",
        ]
        assert queue["items"][1]["review_by"] == Clock.day.isoformat()  # Today still eligible.
        assert queue["items"][2]["review_by"] == (Clock.day + timedelta(days=7)).isoformat()
        assert client.get(route + "/sources", headers=headers()).json() == before
        assert (
            client.get(route + "/sources/" + ids[0] + "/reviews", headers=headers()).json()[
                "events"
            ]
            == []
        )
        assert client.get(route + "/review-queue", headers=headers("b-manager")).json()[
            "summary"
        ] == {"overdue": 1, "due_soon": 0, "current": 0, "undated": 0}
        # Renew and remove through existing actions; a fresh check must reflect both.
        changed = client.patch(
            route + "/sources/" + ids[0] + "/review",
            headers=headers(),
            json={"review_by": "2030-02-01", "reviewed": True},
        )
        assert changed.status_code == 200
        client.delete(route + "/sources/" + ids[1], headers=headers())
        refreshed = client.get(route + "/review-queue", headers=headers()).json()
        assert refreshed["summary"] == {"overdue": 0, "due_soon": 1, "current": 2, "undated": 1}
        assert [item["id"] for item in refreshed["items"]] == [ids[2]]


def test_empty_queue_auth_and_unknown_agent(tmp_path):
    with workspace(tmp_path / "sources.sqlite3") as client:
        route = f"{BASE}/documents/review-queue"
        assert client.get(route).status_code == 401
        assert client.get(f"{BASE}/unknown/review-queue", headers=headers()).status_code == 404
        result = client.get(route, headers=headers()).json()
        assert result["items"] == []
        assert result["summary"] == {"overdue": 0, "due_soon": 0, "current": 0, "undated": 0}
