"""JSON source deadlines require calendar dates rather than timestamp coercion."""

from datetime import date

import pytest

from knowledge.agent_data.catalogue import dataset_ids
from tests.security.test_assigned_source_api_isolation import BASE, headers, workspace


@pytest.mark.parametrize("deadline", [1893456000, "2030-01-01T00:00:00Z"])
def test_non_calendar_json_deadlines_are_rejected(tmp_path, deadline):
    with workspace(tmp_path / "sources.sqlite3") as client:
        response = client.post(
            f"{BASE}/documents/sources",
            headers=headers(),
            json={
                "kind": "text",
                "title": "Fictional calendar fixture",
                "text": "Fictional calendarmarker gardens allow visits.",
                "review_by": deadline,
            },
        )
        assert response.status_code == 422, response.text
        assert client.get(f"{BASE}/documents/sources", headers=headers()).json()["sources"] == []


@pytest.mark.parametrize("agent", dataset_ids())
def test_all_agents_keep_deadlines_through_rejected_coercions_and_renew_explicitly(
    tmp_path, monkeypatch, agent
):
    class Clock(date):
        day = date(2030, 1, 2)

        @classmethod
        def today(cls):
            return cls.day

    monkeypatch.setattr("knowledge.assigned_sources.date", Clock)
    path = tmp_path / "sources.sqlite3"
    route = f"{BASE}/{agent}"
    body = {
        "kind": "text",
        "title": "Fictional calendar policy",
        "text": "Fictional calendarmarker gardens allow two visits.",
        "customer_safe": True,
    }
    with workspace(path) as client:
        for identity in ["a-manager", "b-manager"]:
            response = client.post(
                route + "/sources",
                headers=headers(identity),
                json={**body, "review_by": "2030-01-02"},
            )
            assert response.status_code == 200, response.text
        before = client.get(route + "/sources", headers=headers()).json()
        foreign_before = client.get(route + "/sources", headers=headers("b-manager")).json()
        for value in [
            1893542400,
            1893542400000,
            1893542400.0,
            "2030-01-03T00:00:00Z",
            "2030-01-03T00:00:00+00:00",
            "2030-02-30",
            True,
            [],
            {},
        ]:
            response = client.post(
                route + "/sources", headers=headers(), json={**body, "review_by": value}
            )
            assert response.status_code == 422, (agent, value, response.text)
            assert client.get(route + "/sources", headers=headers()).json() == before
            assert (
                client.get(route + "/sources", headers=headers("b-manager")).json()
                == foreign_before
            )
        # Omitted/null imports cannot erase an existing date or revive it next day.
        for patch in [{}, {"review_by": None}]:
            response = client.post(route + "/sources", headers=headers(), json={**body, **patch})
            assert (
                response.status_code == 200
                and response.json()["source"]["review_by"] == "2030-01-02"
            )
        source_id = before["sources"][0]["id"]

        def answer():
            return client.post(
                route + "/answer",
                headers=headers("a-viewer"),
                json={"question": "calendarmarker gardens", "audience": "customer"},
            ).json()

        assert answer()["answered"]
    Clock.day = date(2030, 1, 3)
    with workspace(path) as client:
        response = client.post(
            route + "/answer",
            headers=headers(),
            json={"question": "calendarmarker gardens", "audience": "customer"},
        )
        assert not response.json()["answered"]
        for patch in [{}, {"review_by": None}]:
            result = client.post(route + "/sources", headers=headers(), json={**body, **patch})
            assert (
                result.status_code == 200 and result.json()["source"]["review_by"] == "2030-01-02"
            )
        assert not client.post(
            route + "/answer",
            headers=headers(),
            json={"question": "calendarmarker gardens", "audience": "customer"},
        ).json()["answered"]
        renewed = client.post(
            route + "/sources", headers=headers(), json={**body, "review_by": "2030-01-05"}
        )
        assert renewed.status_code == 200 and renewed.json()["source"]["id"] == source_id
        assert renewed.json()["source"]["review_by"] == "2030-01-05"
        assert client.post(
            route + "/answer",
            headers=headers(),
            json={"question": "calendarmarker gardens", "audience": "customer"},
        ).json()["answered"]
        assert client.get(route + "/sources", headers=headers("b-manager")).json() == foreign_before


def test_invalid_website_calendar_is_rejected_before_fetch(tmp_path, monkeypatch):
    fetched = []

    def website(url):
        fetched.append(url)
        return ["Fictional calendarmarker website policy."], url

    monkeypatch.setattr("apps.api.app.api.v1.routes.agent_knowledge.import_website", website)
    with workspace(tmp_path / "sources.sqlite3") as client:
        body = {
            "kind": "website",
            "title": "Fictional website calendar",
            "url": "https://example.test/fictional",
        }
        for value in [1893456000, "2030-01-01T00:00:00Z", "2030-02-30"]:
            response = client.post(
                f"{BASE}/documents/sources", headers=headers(), json={**body, "review_by": value}
            )
            assert response.status_code == 422, response.text
        assert fetched == []
        assert client.get(f"{BASE}/documents/sources", headers=headers()).json()["sources"] == []
        accepted = client.post(
            f"{BASE}/documents/sources", headers=headers(), json={**body, "review_by": "2030-01-05"}
        )
        assert accepted.status_code == 200 and fetched == [body["url"]]


def test_new_sources_can_remain_undated_with_omitted_or_null_date(tmp_path):
    with workspace(tmp_path / "sources.sqlite3") as client:
        for i, patch in enumerate([{}, {"review_by": None}]):
            response = client.post(
                f"{BASE}/documents/sources",
                headers=headers(),
                json={
                    "kind": "text",
                    "title": f"Fictional undated {i}",
                    "text": f"Fictional undated policy {i}.",
                    **patch,
                },
            )
            assert response.status_code == 200 and response.json()["source"]["review_by"] is None
