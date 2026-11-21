"""Redis readiness fails closed on setup, ping and cleanup errors."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import create_app
from core.cache.redis import ping_redis


class RedisReadinessProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_ping_result_is_preserved_and_client_is_closed(self):
        for result in (True, False):
            with self.subTest(result=result):
                client = SimpleNamespace(ping=AsyncMock(return_value=result), aclose=AsyncMock())
                with patch("core.cache.redis.create_redis_client", return_value=client):
                    self.assertIs(await ping_redis(object()), result)
                client.aclose.assert_awaited_once()

    async def test_client_creation_failure_reports_unavailable(self):
        with patch("core.cache.redis.create_redis_client", side_effect=ValueError("fixture-setup")):
            self.assertFalse(await ping_redis(object()))

    async def test_ping_and_cleanup_failures_report_unavailable(self):
        for ping_fails, close_fails in ((True, False), (False, True), (True, True)):
            with self.subTest(ping_fails=ping_fails, close_fails=close_fails):
                client = SimpleNamespace(
                    ping=AsyncMock(
                        return_value=True,
                        side_effect=OSError("fixture-ping") if ping_fails else None,
                    ),
                    aclose=AsyncMock(side_effect=OSError("fixture-close") if close_fails else None),
                )
                with patch("core.cache.redis.create_redis_client", return_value=client):
                    self.assertFalse(await ping_redis(object()))
                client.aclose.assert_awaited_once()

    async def test_ping_cancellation_propagates_and_still_closes_client(self):
        client = SimpleNamespace(
            ping=AsyncMock(side_effect=asyncio.CancelledError), aclose=AsyncMock()
        )
        with (
            patch("core.cache.redis.create_redis_client", return_value=client),
            self.assertRaises(asyncio.CancelledError),
        ):
            await ping_redis(object())
        client.aclose.assert_awaited_once()

    async def test_cleanup_cancellation_propagates(self):
        client = SimpleNamespace(
            ping=AsyncMock(return_value=True), aclose=AsyncMock(side_effect=asyncio.CancelledError)
        )
        with (
            patch("core.cache.redis.create_redis_client", return_value=client),
            self.assertRaises(asyncio.CancelledError),
        ):
            await ping_redis(object())


@pytest.mark.parametrize("failure", ["setup", "cleanup"])
def test_ready_reports_redis_unavailable_instead_of_internal_error(settings, monkeypatch, failure):
    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr("apps.api.app.api.v1.routes.health.create_engine", lambda _: engine)
    monkeypatch.setattr(
        "apps.api.app.api.v1.routes.health.ping_database", AsyncMock(return_value=True)
    )
    if failure == "setup":
        factory = Mock(side_effect=ValueError("fixture-redis-setup-error"))
    else:
        factory = Mock(
            return_value=SimpleNamespace(
                ping=AsyncMock(return_value=True),
                aclose=AsyncMock(side_effect=OSError("fixture-redis-close-error")),
            )
        )
    monkeypatch.setattr("core.cache.redis.create_redis_client", factory)
    app = create_app(settings.model_copy(update={"readiness_checks_required": True}))
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"] == [
        {"name": "postgres", "status": "ok"},
        {"name": "redis", "status": "unavailable"},
    ]
    assert "fixture-redis" not in response.text
    assert response.headers["X-Frame-Options"] == "DENY"
    engine.dispose.assert_awaited_once()
