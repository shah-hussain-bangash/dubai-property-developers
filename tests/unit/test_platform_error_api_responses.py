"""Full API responses preserve headers while suppressing platform 5xx diagnostics."""

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import create_app
from core.exceptions.errors import AgentTimeoutError, ConfigurationError, IntegrationError


@pytest.mark.parametrize("error_type", [ConfigurationError, IntegrationError, AgentTimeoutError])
def test_platform_server_errors_remain_private_and_correlated(settings, error_type):
    origin, correlation = "https://frontend.example.com", "fixture-correlation-123"
    app = create_app(settings.model_copy(update={"cors_allowed_origins": [origin]}))
    error = error_type(
        "fixture-private-server-detail", details={"internal": "fixture-hidden-payload"}
    )

    @app.get("/fixture-platform-error")
    async def fail():
        raise error

    with TestClient(app) as client:
        response = client.get(
            "/fixture-platform-error",
            headers={"Origin": origin, "X-Correlation-ID": correlation},
        )
    assert response.status_code == error.status_code
    assert response.json()["error"] == {
        "code": error.code,
        "message": "An unexpected error occurred",
        "details": {},
        "correlation_id": correlation,
    }
    assert "fixture-private-server-detail" not in response.text
    assert "fixture-hidden-payload" not in response.text
    assert response.headers["X-Correlation-ID"] == correlation
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Access-Control-Allow-Origin"] == origin
