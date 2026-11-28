"""JSON customer-source approval must not use boolean coercion."""

import pytest

from knowledge.agent_data.catalogue import dataset_ids
from tests.security.test_assigned_source_api_isolation import BASE, headers, workspace


@pytest.mark.parametrize("approval", ["yes", 1])
def test_coerced_json_approval_is_rejected(tmp_path, approval):
    with workspace(tmp_path / "sources.sqlite3") as client:
        response = client.post(
            f"{BASE}/documents/sources",
            headers=headers(),
            json={
                "kind": "text",
                "title": "Fictional explicit approval",
                "text": "Fictional explicitflag gardens allow two visits.",
                "customer_safe": approval,
            },
        )
        assert response.status_code == 422, response.text
        assert client.get(f"{BASE}/documents/sources", headers=headers()).json()["sources"] == []


@pytest.mark.parametrize("agent", dataset_ids())
def test_all_agents_require_boolean_approval_without_changing_existing_sources(tmp_path, agent):
    route = f"{BASE}/{agent}"
    body = {
        "kind": "text",
        "title": "Fictional approval policy",
        "text": "Fictional explicitflag gardens allow two visits.",
    }
    with workspace(tmp_path / "sources.sqlite3") as client:
        own = client.post(
            route + "/sources", headers=headers(), json={**body, "customer_safe": True}
        )
        foreign = client.post(
            route + "/sources", headers=headers("b-manager"), json={**body, "customer_safe": True}
        )
        assert own.status_code == foreign.status_code == 200
        source_id = own.json()["source"]["id"]
        before = client.get(route + "/sources", headers=headers()).json()
        foreign_before = client.get(route + "/sources", headers=headers("b-manager")).json()
        for value in [0, 1, "yes", "true", "false", None, {}, []]:
            response = client.post(
                route + "/sources", headers=headers(), json={**body, "customer_safe": value}
            )
            assert response.status_code == 422, (agent, value, response.text)
            assert client.get(route + "/sources", headers=headers()).json() == before
            assert (
                client.get(route + "/sources", headers=headers("b-manager")).json()
                == foreign_before
            )

        def answer(question, audience="customer"):
            r = client.post(
                route + "/answer",
                headers=headers("a-viewer"),
                json={"question": question, "audience": audience},
            )
            assert r.status_code == 200, r.text
            return r.json()

        assert [s["source_id"] for s in answer("explicitflag gardens")["sources"]] == [source_id]
        staff_only = client.post(
            route + "/sources", headers=headers(), json={**body, "customer_safe": False}
        )
        assert staff_only.status_code == 200 and staff_only.json()["source"]["customer_safe"] == 0
        assert not answer("explicitflag gardens")["answered"]
        assert answer("explicitflag gardens", "staff")["answered"]
        approved = client.post(
            route + "/sources", headers=headers(), json={**body, "customer_safe": True}
        )
        assert approved.status_code == 200 and approved.json()["source"]["customer_safe"] == 1
        assert answer("explicitflag gardens")["answered"]
        default = client.post(
            route + "/sources",
            headers=headers(),
            json={
                "kind": "text",
                "title": "Fictional default policy",
                "text": "Fictional defaultflag balcony has staff rules.",
            },
        )
        assert default.status_code == 200 and default.json()["source"]["customer_safe"] == 0
        assert not answer("defaultflag balcony")["answered"]
        assert answer("defaultflag balcony", "staff")["answered"]
        assert client.get(route + "/sources", headers=headers("b-manager")).json() == foreign_before
        history = client.get(route + "/sources/" + source_id + "/reviews", headers=headers()).json()
        assert history["events"] == []


def test_invalid_website_approval_is_rejected_before_fetching(tmp_path, monkeypatch):
    fetched = []

    def website(url):
        fetched.append(url)
        return ["Fictional websiteflag gardens allow two visits."], url

    monkeypatch.setattr("apps.api.app.api.v1.routes.agent_knowledge.import_website", website)
    body = {
        "kind": "website",
        "title": "Fictional website policy",
        "url": "https://example.test/fictional",
    }
    with workspace(tmp_path / "sources.sqlite3") as client:
        for value in [0, 1, "yes", "true", "false", None, {}, []]:
            response = client.post(
                f"{BASE}/documents/sources",
                headers=headers(),
                json={**body, "customer_safe": value},
            )
            assert response.status_code == 422, response.text
        assert fetched == []
        assert client.get(f"{BASE}/documents/sources", headers=headers()).json()["sources"] == []
        approved = client.post(
            f"{BASE}/documents/sources", headers=headers(), json={**body, "customer_safe": True}
        )
        assert approved.status_code == 200 and approved.json()["source"]["customer_safe"] == 1
        assert fetched == [body["url"]]


def test_raw_text_upload_keeps_its_existing_query_parameter_contract(tmp_path):
    with workspace(tmp_path / "sources.sqlite3") as client:
        for flag, expected in [("true", 1), ("false", 0), (None, 0)]:
            params = {"title": "Fictional raw " + str(flag)}
            if flag is not None:
                params["customer_safe"] = flag
            response = client.post(
                f"{BASE}/documents/sources",
                headers={**headers(), "Content-Type": "text/plain"},
                params=params,
                content=f"Fictional rawflag {flag} policy.".encode(),
            )
            assert response.status_code == 200, response.text
            assert response.json()["source"]["customer_safe"] == expected
