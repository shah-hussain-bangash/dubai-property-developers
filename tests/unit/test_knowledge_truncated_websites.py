"""Premature EOF must not turn a partial website into saved agent knowledge."""

import http.client
import io
import socket

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import create_app
from core.exceptions.errors import DomainValidationError
from knowledge.ingestion import assigned_inputs

TEXT = b"Fictional garden policy permits two visits."


@pytest.fixture
def website(monkeypatch):
    pending, connections = [], []

    class Socket:
        def __init__(self, raw):
            self.raw = raw

        def makefile(self, *_):
            return io.BytesIO(self.raw)

    class Connection:
        def __init__(self, *_):
            self.closed = False
            self.response = http.client.HTTPResponse(Socket(pending.pop(0)))
            self.response.begin()
            connections.append(self)

        def request(self, *_args, **_kwargs):
            pass

        def getresponse(self):
            return self.response

        def close(self):
            self.closed = True
            self.response.close()

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443))],
    )
    monkeypatch.setattr(assigned_inputs, "PinnedHTTPS", Connection)
    return pending, connections


def response(mime, body, framing):
    return b"HTTP/1.1 200 OK\r\nContent-Type: " + mime.encode() + b"\r\n" + framing + b"\r\n" + body


@pytest.mark.parametrize("mime", ["text/plain", "text/html"])
def test_premature_eof_rejects_partial_page(website, mime):
    pending, connections = website
    pending.append(response(mime, TEXT, b"Content-Length: 900\r\n"))
    with pytest.raises(DomainValidationError, match="incomplete"):
        assigned_inputs.import_website("https://example.test/policy")
    assert connections[0].closed


@pytest.mark.parametrize("mime", ["text/plain", "text/html"])
def test_truncated_page_is_not_saved_or_answered(website, settings, tmp_path, mime):
    pending, connections = website
    pending.append(response(mime, TEXT, b"Content-Length: 900\r\n"))
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    with TestClient(create_app(settings)) as client:
        base = "/api/v1/knowledge/agents/documents"
        result = client.post(
            base + "/sources",
            json={
                "title": "Fictional truncated page",
                "kind": "website",
                "url": "https://example.test/policy",
            },
        )
        assert result.status_code == 422, result.text
        assert result.json()["error"]["code"] == "validation_error"
        assert "incomplete" in result.json()["error"]["message"]
        assert client.get(base + "/sources").json()["sources"] == []
        answer = client.post(base + "/answer", json={"question": "garden policy"}).json()
        assert not answer["answered"] and answer["sources"] == []
    assert connections[0].closed


@pytest.mark.parametrize("framing", ["length", "close", "chunked"])
def test_complete_response_framing_remains_supported(website, framing):
    pending, connections = website
    headers = b""
    body = TEXT
    if framing == "length":
        headers = f"Content-Length: {len(TEXT)}\r\n".encode()
    elif framing == "chunked":
        headers = b"Transfer-Encoding: chunked\r\n"
        body = f"{len(TEXT):x}\r\n".encode() + TEXT + b"\r\n0\r\n\r\n"
    pending.append(response("text/plain", body, headers))
    assert assigned_inputs.import_website("https://example.test/policy") == (
        [TEXT.decode()],
        "https://example.test/policy",
    )
    assert connections[0].closed


def test_truncated_chunked_response_is_also_rejected(website):
    pending, connections = website
    pending.append(response("text/plain", b"ff\r\n" + TEXT, b"Transfer-Encoding: chunked\r\n"))
    with pytest.raises(DomainValidationError):
        assigned_inputs.import_website("https://example.test/policy")
    assert connections[0].closed
