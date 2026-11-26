"""Natural question wrappers and common word forms preserve source-only answers."""

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import create_app
from knowledge.agent_data.catalogue import dataset_ids
from knowledge.assigned_sources import AssignedSources

CASES = [
    ("Fictional garden policy permits two visits.", "Please tell me about garden visits"),
    ("Fictional payment plans allow monthly installments.", "Could you explain the payment plan?"),
    ("Fictional viewing bookings need approval.", "Explain viewing booking"),
    ("Fictional reservation requires instalments.", "Please explain reservation installments"),
    ("Fictional deposits follow payment schedules.", "Tell me about deposit payment"),
    ("Fictional apartments have two bedrooms.", "Could you tell me about apartment bedrooms?"),
    ("Fictional documents describe viewing fees.", "Would you explain document viewing fees?"),
    ("Fictional enquiries require a booking.", "Tell me about enquiry bookings"),
    ("Fictional canceled viewings need review.", "Please explain cancelled viewing"),
    ("Fictional villa gardens open weekly.", "Could you please tell me about villa gardens?"),
]


@pytest.mark.parametrize("text,question", CASES)
def test_supported_wording_returns_only_the_exact_original_passage(tmp_path, text, question):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    source = store.add("fixture", "documents", "Fictional approved guide", "text", [text])
    result = store.answer("fixture", "documents", question)
    assert result["answered"] and result["text"] == "[1] " + text
    assert [s["source_id"] for s in result["sources"]] == [source["id"]]
    assert result["method"] == "source-excerpts" and result["sent"] is False


@pytest.mark.parametrize("agent", dataset_ids())
def test_wording_does_not_borrow_foreign_or_unapproved_material(tmp_path, agent):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    other = "email" if agent != "email" else "documents"
    text = "Fictional garden policy permits two visits."
    question = "Please tell me about garden visits"
    own = store.add("fixture", agent, "Own source", "text", [text])
    store.add("foreign", agent, "Other organization", "text", [text], customer_safe=True)
    store.add("fixture", other, "Other agent", "text", [text], customer_safe=True)
    assert store.answer("fixture", agent, question)["answered"]
    assert store.tool_search("fixture", agent, question)["citations"] == []
    store.add("fixture", agent, "Own approved source", "text", [text], customer_safe=True)
    result = store.tool_search("fixture", agent, question)
    assert [c["title"] for c in result["citations"]] == ["Own approved source"]
    store.remove("fixture", agent, own["id"])
    assert not store.answer("fixture", agent, question)["answered"]


@pytest.mark.parametrize(
    "text,question",
    [
        ("Fictional garden policy permits visits.", "Please tell me about garden cancellation"),
        ("Fictional profile documents.", "file"),
        ("Fictional apartment fees.", "flat fees"),
        ("Fictional r and sum markers.", "résumé"),
        ("Please tell me about.", "Please tell me about"),
    ],
)
def test_unsupported_or_filler_only_queries_still_abstain(tmp_path, text, question):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    store.add("fixture", "documents", "Fictional guide", "text", [text])
    result = store.answer("fixture", "documents", question)
    assert not result["answered"] and result["sources"] == []


def test_http_answer_keeps_original_spelling_and_excerpt(settings, tmp_path):
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    with TestClient(create_app(settings)) as client:
        base = "/api/v1/knowledge/agents/documents"
        text = "Fictional reservation requires instalments."
        saved = client.post(
            base + "/sources",
            json={
                "title": "Fictional reservation",
                "kind": "text",
                "text": text,
            },
        )
        assert saved.status_code == 200
        result = client.post(
            base + "/answer",
            json={
                "question": "Please explain reservation installments",
            },
        ).json()
        assert result["text"] == "[1] " + text and result["sent"] is False
        assert result["sources"][0]["source_id"] == saved.json()["source"]["id"]
