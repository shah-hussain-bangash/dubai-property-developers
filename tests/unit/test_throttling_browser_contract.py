"""Browser-visible throttling provides correlated errors and backoff metadata."""

import re

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import create_app

ORIGIN = "https://frontend.example.com"


@pytest.fixture
def throttled_client(settings, monkeypatch):
    monkeypatch.setattr("apps.api.app.middleware.rate_limit.time.time", lambda: 1700000000.0)
    configured = settings.model_copy(
        update={"rate_limit_per_minute": 1, "cors_allowed_origins": [ORIGIN]}
    )
    with TestClient(create_app(configured)) as client:
        assert client.get("/api/v1/agents").status_code == 200
        yield client


@pytest.mark.parametrize("incoming", ["fixture-correlation-123", None, "fixture invalid id"])
def test_browser_can_read_retry_guidance_and_matching_error_id(throttled_client, incoming):
    headers = {"Origin": ORIGIN}
    if incoming is not None:
        headers["X-Correlation-ID"] = incoming
    response = throttled_client.get("/api/v1/agents", headers=headers)
    assert response.status_code == 429
    error = response.json()["error"]
    correlation = response.headers["X-Correlation-ID"]
    assert error["correlation_id"] == correlation
    assert error["code"] == "rate_limited"
    assert response.headers["Retry-After"] == "60"
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    exposed = {
        name.strip().lower()
        for name in response.headers["Access-Control-Expose-Headers"].split(",")
    }
    assert {"x-correlation-id", "retry-after"} <= exposed
    if incoming == "fixture-correlation-123":
        assert correlation == incoming
    else:
        assert re.fullmatch(r"[0-9a-f]{32}", correlation)
        assert correlation != incoming


def test_throttled_response_does_not_authorize_disallowed_origin(throttled_client):
    response = throttled_client.get(
        "/api/v1/agents",
        headers={
            "Origin": "https://untrusted.example.com",
            "X-Correlation-ID": "fixture-request-123",
        },
    )
    assert response.status_code == 429
    assert "Access-Control-Allow-Origin" not in response.headers
    assert response.json()["error"]["correlation_id"] == response.headers["X-Correlation-ID"]


def test_non_browser_throttling_uses_the_same_error_contract(throttled_client):
    response = throttled_client.get("/api/v1/agents")
    assert response.status_code == 429
    assert response.json()["error"]["correlation_id"] == response.headers["X-Correlation-ID"]
    assert response.headers["Retry-After"] == "60"
