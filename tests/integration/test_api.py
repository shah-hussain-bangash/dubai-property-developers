"""In-process API tests (FastAPI TestClient, mock integrations; no network or DB)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from core.config.settings import Environment, Settings
from tests.factories import lead_payload


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok" and body["environment"] == "test"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Correlation-ID"]


def test_correlation_id_is_echoed_when_well_formed(client: TestClient) -> None:
    good = client.get("/health", headers={"X-Correlation-ID": "abc12345-test"})
    assert good.headers["X-Correlation-ID"] == "abc12345-test"
    bad = client.get("/health", headers={"X-Correlation-ID": "<script>"})
    assert bad.headers["X-Correlation-ID"] != "<script>"


def test_ready_reports_skipped_dependencies(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded" and body["agents_registered"] == 13


def test_list_agents(client: TestClient) -> None:
    body = client.get("/api/v1/agents").json()
    assert body["total"] == 13
    ids = {a["agent_id"] for a in body["items"]}
    assert {"supervisor", "voice", "analytics"} <= ids
    assert all(a["implementation_status"] in {"functional", "partial", "interface_only"} for a in body["items"])


def test_list_workflows(client: TestClient) -> None:
    body = client.get("/api/v1/workflows").json()
    assert body["total"] >= 6
    lead = next(w for w in body["items"] if w["workflow_id"] == "lead_processing")
    assert lead["implementation_status"] == "functional"


def test_demo_process_runs_lead_workflow(client: TestClient) -> None:
    response = client.post("/api/v1/leads/demo-process", json=lead_payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dev_only"] is True and body["uses_mock_integrations"] is True
    assert body["status"] == "succeeded"
    assert body["result"]["qualification"]["score"]["category"] == "hot"
    assert body["result"]["crm"]["external_id"].startswith("mock-lead-")


def test_demo_process_validation_error_is_structured(client: TestClient) -> None:
    response = client.post("/api/v1/leads/demo-process", json={"full_name": "No Contact"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error" and error["correlation_id"]


def test_rbac_denies_viewer(client: TestClient) -> None:
    response = client.post(
        "/api/v1/leads/demo-process", json=lead_payload(), headers={"X-Dev-Roles": "viewer"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_approvals_require_permission_and_list(client: TestClient) -> None:
    assert client.get("/api/v1/approvals/pending", headers={"X-Dev-Roles": "analyst"}).status_code == 403
    assert client.get("/api/v1/approvals/pending").json() == []


def test_dev_routes_absent_when_disabled(settings: Settings) -> None:
    from apps.api.app.main import create_app

    app = create_app(settings.model_copy(update={"enable_dev_routes": False}))
    with TestClient(app) as c:
        assert c.post("/api/v1/leads/demo-process", json=lead_payload()).status_code == 404


def test_token_mode_fails_closed(settings: Settings) -> None:
    from apps.api.app.main import create_app

    app = create_app(settings.model_copy(update={"auth_mode": "token"}))
    with TestClient(app) as c:
        assert c.get("/api/v1/agents").status_code == 401
        assert c.get("/api/v1/agents", headers={"Authorization": "Bearer x"}).status_code == 401


def test_production_refuses_unsafe_config(settings: Settings) -> None:
    import pytest

    from apps.api.app.main import create_app
    from core.exceptions.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        create_app(settings.model_copy(update={"environment": Environment.PRODUCTION}))
