"""Knowledge imports preserve readable Unicode and never silently replace bad bytes."""

import codecs

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import create_app
from core.exceptions.errors import DomainValidationError
from knowledge.ingestion.assigned_inputs import extract_input

TEXT = "Fictional garden policy — دبي: زيارتان. Café."
ENCODINGS = [
    ("utf-8", b""),
    ("utf-8-sig", b""),
    ("utf-16-le", codecs.BOM_UTF16_LE),
    ("utf-16-be", codecs.BOM_UTF16_BE),
    ("utf-32-le", codecs.BOM_UTF32_LE),
    ("utf-32-be", codecs.BOM_UTF32_BE),
]


@pytest.mark.parametrize("encoding,bom", ENCODINGS)
def test_plain_text_preserves_unicode_without_a_bom_in_knowledge(encoding, bom):
    assert extract_input(bom + TEXT.encode(encoding), "text/plain") == [TEXT]


@pytest.mark.parametrize("encoding,bom", [ENCODINGS[1], ENCODINGS[3]])
def test_html_keeps_unicode_and_excludes_hidden_script(encoding, bom):
    html = "<p>" + TEXT + "</p><script>Fictional hidden command</script>"
    pages = extract_input(bom + html.encode(encoding), "text/html")
    assert TEXT in pages[0]
    assert "hidden command" not in pages[0] and "\ufffd" not in pages[0]


def test_markdown_preserves_bom_marked_unicode():
    text = "# Fictional policy\n" + TEXT
    assert extract_input(codecs.BOM_UTF16_LE + text.encode("utf-16-le"), "text/markdown") == [text]


@pytest.mark.parametrize(
    "data",
    [
        b"\xffnot UTF-8",
        b"Fictional garden \xe2\x82",
        codecs.BOM_UTF16_LE + b"A",
        codecs.BOM_UTF32_LE + b"A",
        codecs.BOM_UTF16_LE + b"\x00\xd8",
        b"Fictional caf\xe9",
    ],
)
def test_malformed_or_unsupported_text_is_rejected_instead_of_replaced(data):
    with pytest.raises(DomainValidationError, match="UTF") as caught:
        extract_input(data, "text/plain")
    assert "Fictional" not in str(caught.value)


@pytest.mark.parametrize("encoding,bom", [ENCODINGS[2], ENCODINGS[5]])
def test_unicode_file_can_be_saved_and_quoted_by_only_its_agent(settings, tmp_path, encoding, bom):
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    with TestClient(create_app(settings)) as client:
        base = "/api/v1/knowledge/agents/documents"
        saved = client.post(
            base + "/sources?title=Fictional%20Unicode%20policy",
            content=bom + TEXT.encode(encoding),
            headers={"Content-Type": "text/plain"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["source"]["chars"] == len(TEXT)
        answer = client.post(base + "/answer", json={"question": "garden policy"}).json()
        assert answer["text"] == "[1] " + TEXT
        assert answer["sources"][0]["excerpt"] == TEXT
        assert answer["sent"] is False
        other = client.post(
            "/api/v1/knowledge/agents/email/answer", json={"question": "garden policy"}
        ).json()
        assert other["answered"] is False


def test_unreadable_upload_returns_validation_error_and_saves_nothing(settings, tmp_path):
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    with TestClient(create_app(settings)) as client:
        base = "/api/v1/knowledge/agents/documents"
        result = client.post(
            base + "/sources?title=Fictional%20invalid%20file",
            content=b"Fictional garden \xe2\x82",
            headers={"Content-Type": "text/plain"},
        )
        assert result.status_code == 422, result.text
        assert result.json()["error"]["code"] == "validation_error"
        assert client.get(base + "/sources").json()["sources"] == []
