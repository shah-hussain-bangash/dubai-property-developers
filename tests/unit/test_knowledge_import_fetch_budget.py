"""A slow response or redirect cannot reset or bypass the website fetch budget."""

import socket
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import create_app
from core.exceptions.errors import DomainValidationError
from knowledge.ingestion import assigned_inputs

TEXT = "Fictional imported garden policy allows two visits."


@pytest.fixture
def website(monkeypatch):
    clock = SimpleNamespace(now=100.0)
    plans, connections, lookups = [], [], []
    # Replace this module's clock reference, not the event loop's global clock.
    monkeypatch.setattr(assigned_inputs, "time", SimpleNamespace(monotonic=lambda: clock.now))

    def resolve(host, *_, **__):
        lookups.append(host)
        clock.now += plans[0].get("dns", 0)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    class Connection:
        def __init__(self, host, address):
            self.plan = plans.pop(0)
            self.closed, self.reads = False, 0
            self.status = self.plan.get("status", 200)
            self.chunks = list(self.plan.get("chunks", [(0, TEXT.encode()), (0, b"")]))
            connections.append(self)
            clock.now += self.plan.get("setup", 0)

        def request(self, *_, **__):
            clock.now += self.plan.get("request", 0)

        def getresponse(self):
            clock.now += self.plan.get("headers", 0)
            return self

        def getheader(self, key, default=""):
            return {
                "Location": self.plan.get("location", "/final"),
                "Content-Type": "text/plain",
            }.get(key, default)

        def read1(self, _):
            self.reads += 1
            delay, data = self.chunks.pop(0)
            clock.now += delay
            return data

        def close(self):
            self.closed = True

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(assigned_inputs, "PinnedHTTPS", Connection)
    return clock, plans, connections, lookups


@pytest.mark.parametrize("stage", ["dns", "setup", "request", "headers", "body", "eof"])
def test_late_network_stage_is_rejected_and_connection_is_closed(website, stage):
    _, plans, connections, _ = website
    plan = (
        {stage: 21}
        if stage not in {"body", "eof"}
        else {
            "chunks": [(21, TEXT.encode()), (0, b"")]
            if stage == "body"
            else [(0, TEXT.encode()), (21, b"")]
        }
    )
    plans.append(plan)
    with pytest.raises(DomainValidationError, match="took too long"):
        assigned_inputs.import_website("https://example.com/source")
    assert all(connection.closed for connection in connections)
    if stage == "dns":
        assert connections == []


def test_redirect_hops_share_one_budget(website):
    _, plans, connections, lookups = website
    plans.extend([{"status": 302, "headers": 11}, {"headers": 10}])
    with pytest.raises(DomainValidationError, match="took too long"):
        assigned_inputs.import_website("https://example.com/start")
    assert len(lookups) == 2 and len(connections) == 2
    assert connections[1].reads == 0
    assert all(connection.closed for connection in connections)


def test_expired_redirect_does_not_start_another_connection(website):
    _, plans, connections, lookups = website
    plans.extend([{"status": 302, "headers": 21}, {}])
    with pytest.raises(DomainValidationError, match="took too long"):
        assigned_inputs.import_website("https://example.com/start")
    assert len(lookups) == len(connections) == 1
    assert connections[0].closed


@pytest.mark.parametrize("delay", [20, 21])
def test_empty_final_read_is_not_a_deadline_bypass(website, delay):
    _, plans, connections, _ = website
    plans.append({"chunks": [(19, TEXT.encode()), (delay - 19, b"")]})
    with pytest.raises(DomainValidationError, match="took too long"):
        assigned_inputs.import_website("https://example.com/source")
    assert connections[0].closed


def test_valid_redirected_response_under_budget_imports_normally(website):
    clock, plans, connections, _ = website
    plans.extend(
        [{"status": 302, "headers": 5}, {"headers": 5, "chunks": [(5, TEXT.encode()), (4, b"")]}]
    )
    pages, uri = assigned_inputs.import_website("https://example.com/start")
    assert pages == [TEXT] and uri == "https://example.com/final"
    assert clock.now == 119
    assert all(connection.closed for connection in connections)


def test_late_import_returns_validation_error_without_saving_source(website, settings, tmp_path):
    _, plans, _, _ = website
    plans.append({"chunks": [(1, TEXT.encode()), (20, b"")]})
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    with TestClient(create_app(settings)) as client:
        base = "/api/v1/knowledge/agents/documents"
        result = client.post(
            base + "/sources",
            json={
                "title": "Fictional late source",
                "kind": "website",
                "url": "https://example.com/source",
            },
        )
        assert result.status_code == 422, result.text
        assert result.json()["error"]["code"] == "validation_error"
        assert "took too long" in result.json()["error"]["message"]
        assert client.get(base + "/sources").json()["sources"] == []
