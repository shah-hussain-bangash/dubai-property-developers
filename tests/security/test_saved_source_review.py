"""Explicit review renews only owned metadata, with fresh customer approval."""

from datetime import date, timedelta

import pytest

from knowledge.agent_data.catalogue import dataset_ids
from knowledge.assigned_sources import AssignedSources
from tests.security.test_assigned_source_api_isolation import BASE, headers, workspace

TEXT = "Fictional reviewed gardens allow two visits."


@pytest.mark.parametrize("agent", dataset_ids())
@pytest.mark.parametrize("approve", [False, True])
def test_review_renews_only_owned_source_and_does_not_inherit_approval(
    tmp_path, monkeypatch, agent, approve
):
    initial_day = date.today()
    new_date = initial_day + timedelta(days=3)
    path = tmp_path / "sources.sqlite3"
    route = f"{BASE}/{agent}"
    with workspace(path) as client:
        original = client.post(
            route + "/sources",
            headers=headers(),
            json={
                "kind": "text",
                "title": "Fictional reviewed source",
                "text": TEXT,
                "review_by": initial_day.isoformat(),
                "customer_safe": True,
            },
        ).json()["source"]
        source_id = original["id"]

    class Tomorrow(date):
        @classmethod
        def today(cls):
            return initial_day + timedelta(days=1)

    monkeypatch.setattr("knowledge.assigned_sources.date", Tomorrow)
    with workspace(path) as client:

        def answered():
            return client.post(
                route + "/answer", headers=headers(), json={"question": "reviewed gardens"}
            ).json()["answered"]

        assert not answered()
        payload = {"review_by": new_date.isoformat(), "reviewed": True}
        if approve:
            payload["customer_safe"] = True
        endpoint = route + "/sources/" + source_id + "/review"
        assert client.patch(endpoint, headers=headers("a-viewer"), json=payload).status_code == 403
        assert client.patch(endpoint, headers=headers("b-manager"), json=payload).status_code == 404
        other = next(a for a in dataset_ids() if a != agent)
        assert (
            client.patch(
                f"{BASE}/{other}/sources/{source_id}/review", headers=headers(), json=payload
            ).status_code
            == 404
        )
        assert not answered()
        result = client.patch(endpoint, headers=headers(), json=payload)
        assert result.status_code == 200, result.text
        assert "no-store" in result.headers["cache-control"]
        updated = result.json()["source"]
        assert result.json()["agent_id"] == agent
        assert updated == {
            **original,
            "review_by": new_date.isoformat(),
            "customer_safe": int(approve),
        }
        assert answered()
        customer_result = AssignedSources(str(path)).tool_search(
            "tenant-a", agent, "reviewed gardens"
        )
        assert bool(customer_result["citations"]) is approve
        snapshot = client.get(route + "/sources/" + source_id, headers=headers()).json()
        assert snapshot["pages"] == [{"page": None, "text": TEXT}]
        assert len(client.get(route + "/sources", headers=headers()).json()["sources"]) == 1
    with workspace(path) as client:
        restored = client.get(route + "/sources/" + source_id, headers=headers()).json()
        assert restored == snapshot


@pytest.mark.parametrize(
    "changes",
    [
        {"reviewed": False},
        {"reviewed": 1},
        {"reviewed": "true"},
        {"review_by": None},
        {"review_by": "2000-01-01"},
        {"review_by": "2030-02-30"},
        {"review_by": 1893456000},
        {"customer_safe": "true"},
        {"text": "replacement"},
        {"tenant_id": "tenant-b"},
        {"review_by": "20300101"},
    ],
)
def test_invalid_review_does_not_change_source(tmp_path, changes):
    with workspace(tmp_path / "sources.sqlite3") as client:
        source = client.post(
            f"{BASE}/documents/sources",
            headers=headers(),
            json={"kind": "text", "title": "Fictional source", "text": TEXT, "customer_safe": True},
        ).json()["source"]
        route = f"{BASE}/documents/sources/{source['id']}"
        body = {
            "review_by": (date.today() + timedelta(days=3)).isoformat(),
            "reviewed": True,
            **changes,
        }
        response = client.patch(route + "/review", headers=headers(), json=body)
        assert response.status_code == 422, response.text
        assert client.get(route, headers=headers()).json()["source"] == source


def test_missing_review_body_auth_unknown_source_and_size(tmp_path):
    with workspace(tmp_path / "sources.sqlite3") as client:
        route = f"{BASE}/documents/sources/missing/review"
        body = {"review_by": (date.today() + timedelta(days=3)).isoformat(), "reviewed": True}
        assert client.patch(route, json=body).status_code == 401
        assert client.patch(route, headers=headers(), json=body).status_code == 404
        assert client.patch(route, headers=headers(), json={}).status_code == 422
        assert client.patch(route, headers=headers(), content=b"invalid").status_code == 422
        assert client.patch(route, headers=headers(), content=b"x" * 2_000_001).status_code == 413
