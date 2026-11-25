"""Supplied-source matching recognizes whole Unicode words without altering excerpts."""

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import create_app
from knowledge.assigned_sources import AssignedSources
from knowledge.embeddings.base import HashingEmbeddingProvider


@pytest.mark.parametrize(
    "text,question",
    [
        ("Fictional café policy allows two visits.", "café"),
        ("الفناء، مفتوح.", "الفناء"),
        ("花园规则", "花园规则"),
        ("Κήπος κανόνες", "κήπος"),
        ("Москва сад", "москва"),
        ("Straße garden policy", "STRASSE"),
    ],
)
def test_unicode_word_matches_its_own_source_verbatim(tmp_path, text, question):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    source = store.add("owner", "documents", "Fictional Unicode guide", "text", [text])
    answer = store.answer("owner", "documents", question)
    assert answer["answered"] and answer["text"] == "[1] " + text
    assert answer["sources"][0]["source_id"] == source["id"]
    assert not store.answer("other", "documents", question)["answered"]
    assert not store.answer("owner", "email", question)["answered"]


@pytest.mark.parametrize("question", ["؟", "،", "؛"])
def test_punctuation_is_not_an_answer_matching_term(tmp_path, question):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    store.add(
        "owner",
        "documents",
        "Fictional punctuation fixture",
        "text",
        ["Fictional garden policy ؟ ، ؛"],
    )
    assert not store.answer("owner", "documents", question)["answered"]


def test_accented_query_does_not_match_unrelated_ascii_fragments(tmp_path):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    store.add(
        "owner",
        "documents",
        "Fictional label guide",
        "text",
        ["Fictional r and sum markers are labels."],
    )
    assert not store.answer("owner", "documents", "résumé")["answered"]


def test_staff_only_and_foreign_unicode_sources_remain_excluded(tmp_path):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    store.add("owner", "documents", "Fictional own staff guide", "text", ["花园规则"])
    store.add("owner", "email", "Fictional other agent", "text", ["花园规则"], customer_safe=True)
    store.add(
        "other", "documents", "Fictional other owner", "text", ["花园规则"], customer_safe=True
    )
    assert store.tool_search("owner", "documents", "花园规则", True)["citations"] == []
    staff = store.tool_search("owner", "documents", "花园规则", False)
    assert [c["title"] for c in staff["citations"]] == ["Fictional own staff guide"]


def test_existing_english_stopword_only_query_stays_unanswered(tmp_path):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    store.add(
        "owner", "documents", "Fictional garden guide", "text", ["What is the garden policy?"]
    )
    assert not store.answer("owner", "documents", "what is the")["answered"]


async def test_legacy_hashing_vectors_keep_their_existing_tokenizer():
    provider = HashingEmbeddingProvider(dimension=32)
    old, fragments = await provider.embed(["résumé", "r sum"])
    assert old == fragments
    assert provider.name == "hashing-bow-32"


def test_unicode_question_can_retrieve_a_saved_source_through_api(settings, tmp_path):
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    with TestClient(create_app(settings)) as client:
        base = "/api/v1/knowledge/agents/documents"
        saved = client.post(
            base + "/sources",
            json={"title": "Fictional Unicode source", "kind": "text", "text": "花园规则"},
        )
        assert saved.status_code == 200
        answer = client.post(base + "/answer", json={"question": "花园规则"}).json()
        assert answer["answered"] and answer["text"] == "[1] 花园规则"
        assert answer["method"] == "source-excerpts" and answer["sent"] is False


@pytest.mark.parametrize(
    "text,expected",
    [
        ("CAFE\u0301 and Straße", ["café", "strasse"]),
        ("حَدِيقَة", ["حَدِيقَة"]),
        ("؟ ، ؛ _ \u0301", []),
    ],
)
def test_canonical_spelling_combining_marks_and_separators(text, expected):
    from knowledge.embeddings.base import tokenize_unicode

    assert tokenize_unicode(text) == expected
