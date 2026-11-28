"""An unchanged re-import cannot silently remove an existing source review deadline."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import create_app
from core.exceptions.errors import PolicyViolationError
from knowledge.assigned_sources import AssignedSources
from workflows.runtime import build_runtime

TEXT = "Fictional garden policy allows two visits."
TITLE = "Fictional garden policy"
REVIEW = date(2030, 1, 1)


def expire(monkeypatch):
    class Later(date):
        @classmethod
        def today(cls):
            return cls(2031, 1, 1)

    monkeypatch.setattr("knowledge.assigned_sources.date", Later)


@pytest.mark.parametrize("metadata", [{}, {"review_by": None}])
def test_omitted_or_null_date_preserves_existing_deadline(tmp_path, metadata):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    first = store.add("owner", "documents", TITLE, "text", [TEXT], review_by=REVIEW)
    duplicate = store.add("owner", "documents", TITLE, "text", [TEXT], **metadata)
    assert duplicate["id"] == first["id"] and duplicate["created"] == first["created"]
    assert duplicate["review_by"] == REVIEW.isoformat()
    assert len(store.list_sources("owner", "documents")) == 1


@pytest.mark.parametrize("kind", ["text", "markdown", "pdf", "website"])
def test_reimport_does_not_restore_expired_source_answers(tmp_path, monkeypatch, kind):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    uri = "https://example.com/gardens" if kind == "website" else None
    first = store.add(
        "owner", "documents", TITLE, kind, [TEXT], uri=uri, review_by=REVIEW, customer_safe=True
    )
    assert store.answer("owner", "documents", "garden policy")["answered"]
    expire(monkeypatch)
    duplicate = store.add("owner", "documents", TITLE, kind, [TEXT], uri=uri, customer_safe=True)
    assert duplicate["id"] == first["id"] and duplicate["review_by"] == REVIEW.isoformat()
    assert not store.answer("owner", "documents", "garden policy")["answered"]
    assert store.tool_search("owner", "documents", "garden policy", True)["citations"] == []


def test_explicit_future_date_can_renew_source_and_undated_sources_remain_supported(
    tmp_path, monkeypatch
):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    first = store.add("owner", "documents", TITLE, "text", [TEXT], review_by=REVIEW)
    expire(monkeypatch)
    renewed = store.add("owner", "documents", TITLE, "text", [TEXT], review_by=date(2032, 1, 1))
    assert renewed["id"] == first["id"] and renewed["review_by"] == "2032-01-01"
    assert store.answer("owner", "documents", "garden policy")["answered"]
    undated = store.add("owner", "email", TITLE, "text", [TEXT])
    assert undated["review_by"] is None


@pytest.mark.parametrize("kind", ["text", "website"])
def test_json_source_reimport_keeps_review_date(settings, tmp_path, monkeypatch, kind):
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    monkeypatch.setattr(
        "apps.api.app.api.v1.routes.agent_knowledge.import_website",
        lambda _: ([TEXT], "https://example.com/gardens"),
    )
    payload = {
        "title": TITLE,
        "kind": kind,
        "customer_safe": True,
        **({"text": TEXT} if kind == "text" else {"url": "https://example.com/gardens"}),
    }
    with TestClient(create_app(settings)) as client:
        path = "/api/v1/knowledge/agents/documents/sources"
        first = client.post(path, json={**payload, "review_by": REVIEW.isoformat()})
        assert first.status_code == 200
        again = client.post(path, json=payload)
        assert again.status_code == 200, again.text
        assert again.json()["source"]["id"] == first.json()["source"]["id"]
        assert again.json()["source"]["review_by"] == REVIEW.isoformat()


@pytest.mark.parametrize("kind,mime", [("text", "text/plain"), ("markdown", "text/markdown")])
def test_raw_file_reimport_cannot_erase_preexisting_review_date(settings, tmp_path, kind, mime):
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    AssignedSources(settings.agent_knowledge_path).add(
        settings.default_tenant_id, "documents", TITLE, kind, [TEXT], review_by=REVIEW
    )
    with TestClient(create_app(settings)) as client:
        result = client.post(
            "/api/v1/knowledge/agents/documents/sources?title=Fictional%20garden%20policy",
            content=TEXT.encode(),
            headers={"Content-Type": mime},
        )
        assert result.status_code == 200, result.text
        assert result.json()["source"]["review_by"] == REVIEW.isoformat()


async def test_reimported_expired_material_cannot_revive_queued_email(
    settings, tmp_path, ctx, monkeypatch
):
    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    runtime = build_runtime(settings)
    await runtime.initialize()
    try:
        store = runtime.assigned_sources
        store.add(
            ctx.tenant_id, "email", TITLE, "text", [TEXT], review_by=REVIEW, customer_safe=True
        )
        queued = await runtime.agents.get("email").run(
            {
                "mode": "send",
                "knowledge_query": "garden policy",
                "recipient_email": "fixture@example.com",
            },
            ctx,
        )
        assert queued.status == "pending_approval"
        expire(monkeypatch)
        store.add(ctx.tenant_id, "email", TITLE, "text", [TEXT], customer_safe=True)
        await runtime.approvals.decide(
            queued.output.approval_id, approved=True, decided_by=ctx.principal.subject
        )
        with pytest.raises(PolicyViolationError):
            await runtime.gateway.execute_approved(queued.output.approval_id, ctx.principal)
        assert runtime.email_sender.outbox == []
    finally:
        await runtime.shutdown()
