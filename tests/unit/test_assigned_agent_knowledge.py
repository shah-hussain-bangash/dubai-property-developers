"""Owner-supplied sources persist, remain scoped, and never trigger model fallback."""

import io
import socket
import subprocess
from datetime import date
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen.canvas import Canvas

from agents.base.context import ExecutionContext
from apps.api.app.main import create_app
from core.config.settings import Environment, Settings
from core.exceptions.errors import DomainValidationError, NotFoundError
from core.security.rbac import Principal, Role
from knowledge.assigned_sources import AssignedSources
from knowledge.ingestion import assigned_inputs
from knowledge.ingestion.assigned_inputs import extract_input, import_website, public_target
from workflows.runtime import build_runtime


def settings(path):
    return Settings(
        _env_file=None,
        environment=Environment.TEST,
        log_json=False,
        agent_knowledge_path=str(path),
        rate_limit_per_minute=10000,
    )


def pdf_bytes(text="Fictional project has eight gardens."):
    output = io.BytesIO()
    canvas = Canvas(output)
    canvas.drawString(40, 750, text)
    canvas.showPage()
    canvas.save()
    return output.getvalue()


def test_sources_are_agent_and_tenant_scoped_and_persist_after_restart(tmp_path):
    path = str(tmp_path / "sources.sqlite3")
    first = AssignedSources(path)
    source = first.add("tenant-a", "documents", "Gardens", "text", ["Project gardens total eight."])
    assert (
        first.add("tenant-a", "documents", "Same", "text", ["Project gardens total eight."])["id"]
        == source["id"]
    )
    second = AssignedSources(path)
    answer = second.answer("tenant-a", "documents", "project gardens")
    assert answer["answered"] and answer["sources"][0]["source_id"] == source["id"]
    assert not second.answer("tenant-a", "marketing", "project gardens")["answered"]
    assert not second.answer("tenant-b", "documents", "project gardens")["answered"]
    assert not second.answer("tenant-a", "documents", "zoology telescope")["answered"]
    with pytest.raises(NotFoundError):
        second.remove("tenant-b", "documents", source["id"])
    second.remove("tenant-a", "documents", source["id"])
    assert not second.answer("tenant-a", "documents", "project gardens")["answered"]


def test_staff_sources_are_excluded_from_customer_replies(tmp_path):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    store.add("a", "documents", "Staff", "text", ["Commission splits remain private."])
    assert store.answer("a", "documents", "commission splits")["answered"]
    assert store.tool_search("a", "documents", "commission splits")["citations"] == []
    store.add(
        "a", "documents", "Public", "text", ["Public gardens total eight."], customer_safe=True
    )
    assert store.tool_search("a", "documents", "public gardens")["citations"]


def test_every_registered_agent_answers_only_its_assigned_material(tmp_path):
    from knowledge.agent_data.catalogue import dataset_ids

    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    for agent in dataset_ids():
        store.add("tenant", agent, "Own guide", "text", [f"Canary project belongs to {agent}."])
    for agent in dataset_ids():
        answer = store.answer("tenant", agent, "canary project")
        assert answer["text"] == f"[1] Canary project belongs to {agent}."
        assert len(answer["sources"]) == 1


def test_duplicate_source_can_change_customer_approval(tmp_path):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    first = store.add("a", "documents", "Guide", "text", ["Public gardens total eight."])
    second = store.add(
        "a",
        "documents",
        "Approved guide",
        "text",
        ["Public gardens total eight."],
        customer_safe=True,
    )
    assert first["id"] == second["id"]
    assert len(store.list_sources("a", "documents")) == 1
    assert store.tool_search("a", "documents", "public gardens")["citations"]


def test_source_validation_and_review_dates(tmp_path):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    for text in ["", " " * 10, "x" * 200001]:
        with pytest.raises(DomainValidationError):
            store.add("a", "documents", "Source", "text", [text])
    with pytest.raises(DomainValidationError):
        store.add("a", "documents", "Source", "text", ["hello"], review_by=date(2000, 1, 1))


def test_pdf_text_and_html_extraction():
    assert "eight gardens" in extract_input(pdf_bytes(), "application/pdf")[0]
    assert (
        "Hidden command"
        not in extract_input(
            b"<p>Visible garden facts</p><script>Hidden command</script>", "text/html"
        )[0]
    )
    for data, mime in [
        (b"invalid", "application/pdf"),
        (b"x" * 2000001, "text/plain"),
        (b"zip", "application/zip"),
    ]:
        with pytest.raises(DomainValidationError):
            extract_input(data, mime)


def test_pdf_parser_timeout_fails_without_leaking_details(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("private command", 15)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(DomainValidationError, match="PDF could not be read") as caught:
        extract_input(b"%PDF-fictional", "application/pdf")
    assert "private command" not in str(caught.value)


def test_expired_sources_are_not_used(tmp_path, monkeypatch):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    store.add(
        "a",
        "documents",
        "Review",
        "text",
        ["Fictional gardens total eight."],
        review_by=date(2030, 1, 1),
    )

    class Later(date):
        @classmethod
        def today(cls):
            return cls(2031, 1, 1)

    monkeypatch.setattr("knowledge.assigned_sources.date", Later)
    assert not store.answer("a", "documents", "fictional gardens")["answered"]
    assert len(store.list_sources("a", "documents")) == 1


def test_https_connection_uses_validated_ip_and_original_tls_hostname(monkeypatch):
    raw = Mock()
    connect = Mock(return_value=raw)
    monkeypatch.setattr(socket, "create_connection", connect)
    connection = assigned_inputs.PinnedHTTPS("example.com", "93.184.216.34")
    connection.tls = Mock()
    connection.connect()
    connect.assert_called_once_with(("93.184.216.34", 443), timeout=8)
    connection.tls.wrap_socket.assert_called_once_with(raw, server_hostname="example.com")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://u:p@example.com",
        "https://example.com:8443",
        "file:///etc/passwd",
        "https://example.com/#fragment",
        "https://example.com/\r\nheader",
    ],
)
def test_website_import_rejects_unsafe_urls(url):
    with pytest.raises(DomainValidationError):
        public_target(url)


@pytest.mark.parametrize(
    "addresses", [["127.0.0.1"], ["169.254.169.254"], ["::1"], ["93.184.216.34", "10.0.0.1"]]
)
def test_dns_must_contain_only_public_addresses(monkeypatch, addresses):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in addresses
        ],
    )
    with pytest.raises(DomainValidationError):
        public_target("https://example.com/page")


def test_website_import_pins_checked_address_and_rechecks_redirects(monkeypatch):
    def lookup(host, *args, **kwargs):
        ip = "127.0.0.1" if host == "private.example" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    connection = Mock()
    response = Mock(status=200)
    response.getheader.side_effect = lambda key, default="": {"Content-Type": "text/html"}.get(
        key, default
    )
    response.read1.side_effect = [b"<p>Fictional garden facts.</p>", b""]
    connection.getresponse.return_value = response
    constructor = Mock(return_value=connection)
    monkeypatch.setattr(assigned_inputs, "PinnedHTTPS", constructor)
    pages, uri = import_website("https://example.com/page")
    assert "garden facts" in pages[0] and uri == "https://example.com/page"
    constructor.assert_called_with("example.com", "93.184.216.34")
    response.status = 302
    response.getheader.side_effect = lambda key, default="": (
        "https://private.example/" if key == "Location" else default
    )
    with pytest.raises(DomainValidationError):
        import_website("https://example.com/page")
    assert constructor.call_count == 2


def test_api_upload_pdf_text_website_answers_and_removal(tmp_path, monkeypatch):
    path = tmp_path / "sources.sqlite3"
    with TestClient(create_app(settings(path))) as client:
        base = "/api/v1/knowledge/agents/documents"
        assert len(client.get("/api/v1/knowledge/agents").json()["agents"]) == 13
        assert (
            client.post(
                base + "/answer", json={"question": "Demo Creek Heights payment plan"}
            ).json()["answered"]
            is False
        )
        imported = client.post(
            base + "/sources?title=Fictional%20PDF",
            content=pdf_bytes(),
            headers={"Content-Type": "application/pdf"},
        )
        assert imported.status_code == 200, imported.text
        source = imported.json()["source"]
        reply = client.post(base + "/answer", json={"question": "project gardens"}).json()
        assert reply["answered"] and reply["sources"][0]["page"] == 1
        assert reply["text"] == "[1] " + reply["sources"][0]["excerpt"]
        assert (
            client.post(
                "/api/v1/knowledge/agents/marketing/answer", json={"question": "project gardens"}
            ).json()["answered"]
            is False
        )
        assert (
            client.post(
                base + "/sources",
                json={"title": "Forbidden", "kind": "text", "text": "data"},
                headers={"X-Dev-Roles": "viewer"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                base + "/sources",
                json={"title": "Spoof", "kind": "text", "text": "data", "tenant_id": "other"},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/knowledge/agents/unknown/sources",
                json={"title": "a", "kind": "text", "text": "a"},
            ).status_code
            == 404
        )
        monkeypatch.setattr(
            "apps.api.app.api.v1.routes.agent_knowledge.import_website",
            lambda url: (["Fictional imported tower has six lifts."], url),
        )
        assert (
            client.post(
                base + "/sources",
                json={"title": "Website", "kind": "website", "url": "https://example.com/tower"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                base + "/sources",
                json={
                    "title": "Text",
                    "kind": "text",
                    "text": "Fictional parking policy allows two cars.",
                },
            ).status_code
            == 200
        )
        assert client.delete(base + "/sources/" + source["id"]).status_code == 200
        assert not client.post(base + "/answer", json={"question": "project gardens"}).json()[
            "answered"
        ]
    with TestClient(create_app(settings(path))) as restarted:
        assert len(restarted.get(base + "/sources").json()["sources"]) == 2


async def test_document_and_sales_agents_never_fall_back_to_demo_facts(tmp_path):
    runtime = build_runtime(settings(tmp_path / "sources.sqlite3"))
    await runtime.initialize()
    principal = Principal(
        subject="manager", tenant_id="demo-org", roles=frozenset({Role.SALES_MANAGER})
    )
    ctx = ExecutionContext(principal=principal, tenant_id="demo-org")
    try:
        properties = await runtime.agents.get("property_recommendation").run({"criteria": {}}, ctx)
        assert properties.output.recommendations == []
        assert properties.output.contains_demo_data is False
        result = await runtime.agents.get("documents").run(
            {"action": "answer", "query": "Demo Creek Heights payment plan"}, ctx
        )
        assert result.status == "escalated" and not result.output.citations
        payload = {
            "message": {
                "conversation_id": "source-test",
                "channel": "web_chat",
                "direction": "inbound",
                "sender": "customer",
                "text": "What is the approved handover date?",
            }
        }
        result = await runtime.agents.get("sales_conversation").run(payload, ctx)
        assert result.status == "escalated" and not result.output.draft.citations
        runtime.assigned_sources.add(
            "demo-org",
            "sales_conversation",
            "Approved facts",
            "text",
            ["The approved handover date is October 2031."],
            customer_safe=True,
        )
        result = await runtime.agents.get("sales_conversation").run(payload, ctx)
        assert (
            result.status == "succeeded"
            and result.output.draft.text == "The approved handover date is October 2031."
        )
        assert result.output.draft.requires_approval and result.output.draft.citations
    finally:
        await runtime.shutdown()
