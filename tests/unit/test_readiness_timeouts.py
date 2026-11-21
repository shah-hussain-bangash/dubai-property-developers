"""Slow readiness dependencies time out without hiding other probe results."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.app.api.v1.routes.health import _probe_with_timeout
from apps.api.app.main import create_app
from core.config.settings import Settings


@pytest.mark.parametrize("value", [0, -1, 31, float("nan"), float("inf"), -float("inf")])
def test_readiness_timeout_rejects_invalid_budgets(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, readiness_probe_timeout_seconds=value)


def test_readiness_timeout_loads_from_environment(monkeypatch):
    monkeypatch.setenv("READINESS_PROBE_TIMEOUT_SECONDS", "0.25")
    assert Settings(_env_file=None).readiness_probe_timeout_seconds == 0.25


@pytest.mark.parametrize(
    "dependency,phase",
    [
        ("postgres", "ping"),
        ("postgres", "cleanup"),
        ("redis", "ping"),
        ("redis", "cleanup"),
    ],
)
def test_slow_probe_reports_unavailable_and_other_dependency_still_runs(
    settings, monkeypatch, dependency, phase
):
    cancelled = Mock()

    async def slow_operation(*args):
        try:
            # A bounded fallback keeps a broken timeout regression from hanging the suite.
            await asyncio.sleep(0.2)
            return True
        except asyncio.CancelledError:
            cancelled()
            raise

    engine = SimpleNamespace(dispose=AsyncMock())
    postgres = AsyncMock(return_value=True)
    redis = SimpleNamespace(ping=AsyncMock(return_value=True), aclose=AsyncMock())
    operations = {
        ("postgres", "ping"): postgres,
        ("postgres", "cleanup"): engine.dispose,
        ("redis", "ping"): redis.ping,
        ("redis", "cleanup"): redis.aclose,
    }
    operations[(dependency, phase)].side_effect = slow_operation
    monkeypatch.setattr("apps.api.app.api.v1.routes.health.create_engine", lambda _: engine)
    monkeypatch.setattr("apps.api.app.api.v1.routes.health.ping_database", postgres)
    monkeypatch.setattr("core.cache.redis.create_redis_client", Mock(return_value=redis))
    configured = settings.model_copy(
        update={"readiness_checks_required": True, "readiness_probe_timeout_seconds": 0.01}
    )
    with TestClient(create_app(configured)) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"] == [
        {"name": name, "status": "unavailable" if name == dependency else "ok"}
        for name in ("postgres", "redis")
    ]
    cancelled.assert_called_once()
    postgres.assert_awaited_once()
    redis.ping.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    redis.aclose.assert_awaited_once()


async def test_external_cancellation_propagates_instead_of_becoming_unavailable():
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def probe():
        started.set()
        try:
            await asyncio.Event().wait()
            return True
        finally:
            cleaned.set()

    task = asyncio.create_task(_probe_with_timeout(probe(), 10))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()
