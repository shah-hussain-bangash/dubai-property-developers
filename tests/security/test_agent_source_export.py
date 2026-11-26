"""Knowledge text downloads preserve saved data without borrowing foreign sources."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest

from knowledge.agent_data.catalogue import dataset_ids
from knowledge.assigned_sources import AssignedSources
from tests.security.test_assigned_source_api_isolation import BASE, headers, workspace


@pytest.mark.parametrize("agent", dataset_ids())
def test_each_agent_exports_all_saved_formats_scoped_read_only_after_restart(tmp_path, agent):
    path = tmp_path / "sources.sqlite3"
    store = AssignedSources(str(path))
    today = date.today()
    other = next(a for a in dataset_ids() if a != agent)
    own = []
    for kind, pages, uri, approved in [
        ("pdf", ["", "Fictional PDF page two 🌴 دبي."], None, True),
        ("markdown", ["# Fictional Markdown policy"], None, False),
        ("website", ["Fictional saved website snapshot."], "https://example.test/fictional", True),
        ("text", ["<script>Fictional plain source text</script>"], None, False),
    ]:
        saved = store.add(
            "tenant-a", agent, "Fictional " + kind, kind, pages, uri, customer_safe=approved
        )
        own.append(saved)
        store.add(
            "tenant-b", agent, "Foreign organization " + kind, kind, pages, uri, customer_safe=True
        )
        store.add(
            "tenant-a",
            other,
            "Foreign agent " + kind,
            kind,
            ["Foreign agent secretmarker."],
            uri,
            customer_safe=True,
        )
    # A reviewed source expires; it remains in the staff text copy.
    reviewed = store.review_source(
        "tenant-a", agent, own[0]["id"], today, True, "fictional-reviewer"
    )
    before = store.list_sources("tenant-a", agent)
    history = store.review_history("tenant-a", agent, own[0]["id"])

    class Tomorrow(date):
        @classmethod
        def today(cls):
            return today + timedelta(days=1)

    with patch("knowledge.assigned_sources.date", Tomorrow), workspace(path) as client:
        route = f"{BASE}/{agent}"
        response = client.get(route + "/export?tenant=tenant-b", headers=headers("a-viewer"))
        assert response.status_code == 200, response.text
        assert "no-store" in response.headers["cache-control"]
        result = response.json()
        assert result["format"] == "agent-source-text-v1" and result["agent_id"] == agent
        assert datetime.fromisoformat(result["exported_at"]).utcoffset() == timedelta(0)
        assert len(result["sources"]) == 4
        assert [item["source"] for item in result["sources"]] == before
        for item in result["sources"]:
            assert item == {
                k: v for k, v in store.read_source("tenant-a", agent, item["source"]["id"]).items()
            }
        pdf = next(item for item in result["sources"] if item["source"]["kind"] == "pdf")
        assert pdf["source"] == reviewed
        assert pdf["pages"] == [
            {"page": 1, "text": ""},
            {"page": 2, "text": "Fictional PDF page two 🌴 دبي."},
        ]
        assert "secretmarker" not in response.text and "fictional-reviewer" not in response.text
        assert "reviews" not in result and "cases" not in result and "tenant" not in result
        # Export format is deliberately distinct from both import and evaluation inputs.
        assert client.post(route + "/sources", headers=headers(), json=result).status_code == 422
        assert client.post(route + "/evaluate", headers=headers(), json=result).status_code == 422
        foreign = client.get(route + "/export", headers=headers("b-manager")).json()
        assert all(
            item["source"]["title"].startswith("Foreign organization")
            for item in foreign["sources"]
        )
        assert store.list_sources("tenant-a", agent) == before
        assert store.review_history("tenant-a", agent, own[0]["id"]) == history
        current = client.post(
            route + "/answer",
            headers=headers(),
            json={"question": "Fictional PDF page", "audience": "customer"},
        ).json()
        assert own[0]["id"] not in {s["source_id"] for s in current["sources"]}
        assert (
            client.delete(route + "/sources/" + own[-1]["id"], headers=headers()).status_code == 200
        )
        after = client.get(route + "/export", headers=headers()).json()
        assert len(after["sources"]) == 3
        assert len(result["sources"]) == 4  # Earlier copy retains its own snapshot.


def test_empty_export_and_auth(tmp_path):
    with workspace(tmp_path / "sources.sqlite3") as client:
        assert client.get(f"{BASE}/documents/export").status_code == 401
        assert client.get(f"{BASE}/unknown/export", headers=headers()).status_code == 404
        response = client.get(f"{BASE}/documents/export", headers=headers())
        assert response.status_code == 200 and response.json()["sources"] == []
