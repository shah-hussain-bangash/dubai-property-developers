"""Unexpected request failures receive the same response protections as other errors."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from apps.api.app.main import create_app
from apps.api.app.middleware.error_response import ErrorResponseMiddleware

ORIGIN = "https://frontend.example.com"
CORRELATION_ID = "fixture-request-123"


@pytest.fixture
def failure_client(settings):
    app = create_app(settings.model_copy(update={"cors_allowed_origins": [ORIGIN]}))

    @app.get("/fixture-failure")
    async def fail():
        raise RuntimeError("fixture-private-error-detail")

    @app.get("/fixture-denied")
    async def deny():
        raise HTTPException(status_code=403, detail="Fixture access denied")

    @app.get("/fixture-validation")
    async def validate(value: int):
        return {"value": value}

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize("origin", [ORIGIN, "https://untrusted.example.com", None])
def test_unhandled_errors_keep_response_headers_without_exposing_details(failure_client, origin):
    headers = {"X-Correlation-ID": CORRELATION_ID}
    if origin is not None:
        headers["Origin"] = origin
    response = failure_client.get("/fixture-failure", headers=headers)
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert error["message"] == "An unexpected error occurred"
    assert error["correlation_id"] == CORRELATION_ID
    assert "fixture-private-error-detail" not in response.text
    assert response.headers["X-Correlation-ID"] == CORRELATION_ID
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
    if origin == ORIGIN:
        assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    else:
        assert "Access-Control-Allow-Origin" not in response.headers


def test_rate_limiter_failure_keeps_structured_response_and_cors(failure_client, monkeypatch):
    monkeypatch.setattr(
        "apps.api.app.middleware.rate_limit.InMemoryFixedWindowRateLimiter.hit",
        AsyncMock(side_effect=RuntimeError("fixture-limiter-error")),
    )
    response = failure_client.get(
        "/api/v1/agents", headers={"Origin": ORIGIN, "X-Correlation-ID": CORRELATION_ID}
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Correlation-ID"] == CORRELATION_ID


def test_handled_http_errors_keep_their_original_status_and_body(failure_client):
    response = failure_client.get("/fixture-denied", headers={"Origin": ORIGIN})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "http_403"
    assert response.json()["error"]["message"] == "Fixture access denied"
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN


def test_validation_errors_keep_their_original_status(failure_client):
    response = failure_client.get("/fixture-validation?value=invalid", headers={"Origin": ORIGIN})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.headers["X-Frame-Options"] == "DENY"


async def test_request_cancellation_is_not_converted_into_server_error():
    middleware = ErrorResponseMiddleware(FastAPI())
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    with pytest.raises(asyncio.CancelledError):
        await middleware.dispatch(request, AsyncMock(side_effect=asyncio.CancelledError))
