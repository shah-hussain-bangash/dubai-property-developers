"""HTTP error privacy retains the application's browser response protections."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.api.app.main import create_app


@pytest.mark.parametrize("status", [401, 500, 503])
def test_http_error_response_remains_correlated_and_header_safe(settings, status):
    origin, correlation = "https://frontend.example.com", "fixture-correlation-123"
    app = create_app(settings.model_copy(update={"cors_allowed_origins": [origin]}))
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else {"Retry-After": "12"}

    @app.get("/fixture-http-error")
    async def fail():
        raise HTTPException(
            status_code=status, detail="fixture-private-http-detail", headers=headers
        )

    with TestClient(app) as client:
        response = client.get(
            "/fixture-http-error",
            headers={"Origin": origin, "X-Correlation-ID": correlation},
        )
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == f"http_{status}"
    assert error["correlation_id"] == correlation
    if status >= 500:
        assert error["message"] == "An unexpected error occurred"
        assert "fixture-private-http-detail" not in response.text
    else:
        assert error["message"] == "fixture-private-http-detail"
    for name, value in headers.items():
        assert response.headers[name] == value
    assert response.headers["X-Correlation-ID"] == correlation
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Access-Control-Allow-Origin"] == origin
