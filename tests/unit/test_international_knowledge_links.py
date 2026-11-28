"""International source links must reach HTTP as ASCII without changing URL meaning."""

import socket

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import create_app
from core.exceptions.errors import DomainValidationError
from knowledge.ingestion import assigned_inputs

TEXT = "Fictional imported garden policy allows two visits."
CASES = [
    ("https://example.com/café", "/caf%C3%A9", "example.com"),
    (
        "https://example.com/دبي?city=دبي",
        "/%D8%AF%D8%A8%D9%8A?city=%D8%AF%D8%A8%D9%8A",
        "example.com",
    ),
    ("https://example.com/房?label=房", "/%E6%88%BF?label=%E6%88%BF", "example.com"),
    (
        "https://example.com/%D8%AF%D8%A8%D9%8A?tag=a%26b",
        "/%D8%AF%D8%A8%D9%8A?tag=a%26b",
        "example.com",
    ),
    (
        "https://example.com/café%2Froom?tag=a%26b&city=دبي",
        "/caf%C3%A9%2Froom?tag=a%26b&city=%D8%AF%D8%A8%D9%8A",
        "example.com",
    ),
    (
        "https://example.com/a;b?tag=a+b&path=%2Froom&v=one%3Dtwo",
        "/a;b?tag=a+b&path=%2Froom&v=one%3Dtwo",
        "example.com",
    ),
    ("https://münich.example/café", "/caf%C3%A9", "xn--mnich-kva.example"),
]


@pytest.fixture
def website(monkeypatch):
    connections, lookups, redirects = [], [], []

    def resolve(host, *_, **__):
        lookups.append(host)
        ip = "127.0.0.1" if host == "private.example" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

    class Response:
        def __init__(self):
            self.location = redirects.pop(0) if redirects else None
            self.status = 302 if self.location else 200
            self.content = ("<p>" + TEXT + "</p>").encode()

        def getheader(self, key, default=""):
            return {"Location": self.location, "Content-Type": "text/html"}.get(key, default)

        def read1(self, limit):
            content, self.content = self.content[:limit], self.content[limit:]
            return content

    class Connection:
        def __init__(self, host, address):
            self.host, self.address, self.target, self.closed = host, address, None, False
            connections.append(self)

        def request(self, method, target, **_):
            # Match the HTTP client's request-line encoding constraint without a socket.
            target.encode("ascii")
            self.target = target

        def getresponse(self):
            return Response()

        def close(self):
            self.closed = True

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(assigned_inputs, "PinnedHTTPS", Connection)
    return connections, lookups, redirects


@pytest.mark.parametrize("url,target,host", CASES)
def test_international_and_preescaped_links_import_exact_page(website, url, target, host):
    connections, lookups, _ = website
    pages, saved_url = assigned_inputs.import_website(url)
    assert TEXT in pages[0] and saved_url == url
    assert lookups == [host]
    assert connections[0].host == host
    assert connections[0].address == "93.184.216.34"
    assert connections[0].target == target
    assert connections[0].closed


@pytest.mark.parametrize(
    "location,host",
    [
        ("/دبي?city=دبي", "example.com"),
        ("https://münich.example/دبي?city=دبي", "xn--mnich-kva.example"),
    ],
)
def test_redirected_international_page_is_encoded_and_rechecked(website, location, host):
    connections, lookups, redirects = website
    redirects.append(location)
    pages, saved = assigned_inputs.import_website("https://example.com/start")
    assert TEXT in pages[0]
    assert saved == ("https://example.com" + location if location.startswith("/") else location)
    assert lookups == ["example.com", host]
    assert connections[1].target == "/%D8%AF%D8%A8%D9%8A?city=%D8%AF%D8%A8%D9%8A"
    assert all(connection.closed for connection in connections)


def test_international_redirect_still_cannot_reach_private_address(website):
    connections, lookups, redirects = website
    redirects.append("https://private.example/دبي")
    with pytest.raises(DomainValidationError, match="public HTTPS"):
        assigned_inputs.import_website("https://example.com/start")
    assert lookups == ["example.com", "private.example"]
    assert len(connections) == 1 and connections[0].closed


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/دبي",
        "https://user@example.com/دبي",
        "https://example.com:8443/دبي",
        "https://example.com/دبي\r\nheader",
        "https://example.com/دبي#fragment",
    ],
)
def test_encoding_does_not_relax_existing_url_restrictions(website, url):
    connections, lookups, _ = website
    with pytest.raises(DomainValidationError):
        assigned_inputs.import_website(url)
    assert connections == lookups == []


def test_international_website_import_is_saved_and_answered_for_selected_agent(
    website, settings, tmp_path
):
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    url = "https://example.com/دبي?tag=a%26b"
    with TestClient(create_app(settings)) as client:
        base = "/api/v1/knowledge/agents/documents"
        saved = client.post(
            base + "/sources",
            json={"title": "Fictional international source", "kind": "website", "url": url},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["source"]["uri"] == url
        answer = client.post(base + "/answer", json={"question": "garden policy"}).json()
        assert answer["answered"] and TEXT in answer["text"]
        assert answer["sources"][0]["uri"] == url and answer["sent"] is False
        other = client.post(
            "/api/v1/knowledge/agents/email/answer", json={"question": "garden policy"}
        ).json()
        assert other["answered"] is False
