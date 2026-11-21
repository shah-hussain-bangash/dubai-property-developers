"""Middleware responses retain browser and security protections under throttling."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import create_app
from core.config.settings import Settings

ORIGIN = "https://frontend.example.com"
HEADERS = {"Origin": ORIGIN, "X-Correlation-ID": "fixture-request-123"}


@pytest.fixture
def limited_client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Keep requests in one fixed rate-limit bucket without timing-sensitive sleeps.
    monkeypatch.setattr("apps.api.app.middleware.rate_limit.time.time", lambda: 1700000000.0)
    configured = settings.model_copy(
        update={"rate_limit_per_minute": 1, "cors_allowed_origins": [ORIGIN]}
    )
    with TestClient(create_app(configured)) as client:
        yield client


def assert_response_headers(response):
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Correlation-ID"] == HEADERS["X-Correlation-ID"]


def test_throttled_response_keeps_cors_security_and_correlation_headers(limited_client):
    assert limited_client.get("/api/v1/agents", headers=HEADERS).status_code == 200
    response = limited_client.get("/api/v1/agents", headers=HEADERS)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert response.headers["Retry-After"] == "60"
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert "X-Correlation-ID" in response.headers["Access-Control-Expose-Headers"]
    assert_response_headers(response)


def test_denied_origin_stays_denied_when_throttled(limited_client):
    headers = {**HEADERS, "Origin": "https://untrusted.example.com"}
    assert limited_client.get("/api/v1/agents", headers=headers).status_code == 200
    response = limited_client.get("/api/v1/agents", headers=headers)
    assert response.status_code == 429
    assert "Access-Control-Allow-Origin" not in response.headers
    assert_response_headers(response)


def test_preflight_remains_available_without_consuming_request_quota(limited_client):
    preflight = {
        **HEADERS,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization",
    }
    response = limited_client.options("/api/v1/agents", headers=preflight)
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert_response_headers(response)
    assert limited_client.get("/api/v1/agents", headers=HEADERS).status_code == 200
    response = limited_client.options("/api/v1/agents", headers=preflight)
    assert response.status_code == 200
    assert_response_headers(response)
    assert limited_client.get("/api/v1/agents", headers=HEADERS).status_code == 429


@pytest.mark.parametrize(("path", "status"), [("/api/v1/agents", 200), ("/fixture-missing", 404)])
def test_regular_responses_keep_existing_headers(limited_client, path, status):
    response = limited_client.get(path, headers=HEADERS)
    assert response.status_code == status
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert_response_headers(response)


def test_health_checks_remain_exempt_from_request_quota(limited_client):
    for _ in range(3):
        response = limited_client.get("/health", headers=HEADERS)
        assert response.status_code == 200
        assert_response_headers(response)
    assert limited_client.get("/api/v1/agents", headers=HEADERS).status_code == 200
    assert limited_client.get("/api/v1/agents", headers=HEADERS).status_code == 429
