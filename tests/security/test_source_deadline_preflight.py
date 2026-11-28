"""Expired import deadlines are rejected before website fetching or extraction."""

from datetime import date

import pytest

from knowledge.agent_data.catalogue import dataset_ids
from tests.security.test_assigned_source_api_isolation import BASE, headers, workspace


@pytest.fixture
def import_calls(monkeypatch):
    class Clock(date):
        @classmethod
        def today(cls):
            return date(2030, 1, 2)

    monkeypatch.setattr("knowledge.assigned_sources.date", Clock)
    calls = []

    def website(url):
        calls.append(("website", url))
        return ["Fictional preflightmarker website policy."], url

    def extract(data, mime):
        calls.append((mime, data))
        return ["Fictional preflightmarker uploaded policy."]

    monkeypatch.setattr("apps.api.app.api.v1.routes.agent_knowledge.import_website", website)
    monkeypatch.setattr("apps.api.app.api.v1.routes.agent_knowledge.extract_input", extract)
    return calls


def submit(client, agent, kind, deadline):
    kwargs = {"headers": headers()}
    if kind == "website":
        body = {
            "title": "Fictional preflight website",
            "kind": kind,
            "url": "https://example.test/fictional",
        }
        if deadline is not None:
            body["review_by"] = deadline
        kwargs["json"] = body
    else:
        mime = {"pdf": "application/pdf", "text": "text/plain", "markdown": "text/markdown"}[kind]
        kwargs["headers"] = {**headers(), "Content-Type": mime}
        kwargs["params"] = {"title": "Fictional preflight upload"}
        if deadline is not None:
            kwargs["params"]["review_by"] = deadline
        kwargs["content"] = b"Fictional extraction input; extraction is stubbed."
    return client.post(f"{BASE}/{agent}/sources", **kwargs)


@pytest.mark.parametrize("agent", dataset_ids())
@pytest.mark.parametrize("kind", ["website", "pdf", "text", "markdown"])
def test_expired_import_deadline_does_no_external_or_extraction_work(
    tmp_path, import_calls, agent, kind
):
    with workspace(tmp_path / "sources.sqlite3") as client:
        seed = {
            "title": "Fictional existing policy",
            "kind": "text",
            "text": "Fictional existing preflightmarker policy.",
            "review_by": "2030-01-02",
            "customer_safe": True,
        }
        for identity in ["a-manager", "b-manager"]:
            assert (
                client.post(
                    f"{BASE}/{agent}/sources", headers=headers(identity), json=seed
                ).status_code
                == 200
            )
        before = {
            identity: client.get(f"{BASE}/{agent}/sources", headers=headers(identity)).json()
            for identity in ["a-manager", "b-manager"]
        }
        response = submit(client, agent, kind, "2030-01-01")
        assert response.status_code == 422, response.text
        assert import_calls == []
        for identity, snapshot in before.items():
            assert (
                client.get(f"{BASE}/{agent}/sources", headers=headers(identity)).json() == snapshot
            )


@pytest.mark.parametrize("kind", ["website", "pdf", "text", "markdown"])
def test_today_future_and_omitted_deadlines_still_import(tmp_path, import_calls, kind):
    with workspace(tmp_path / "sources.sqlite3") as client:
        for deadline in [None, "2030-01-02", "2030-01-03"]:
            import_calls.clear()
            response = submit(client, "documents", kind, deadline)
            assert response.status_code == 200, response.text
            assert len(import_calls) == 1
            assert response.json()["source"]["review_by"] == deadline
