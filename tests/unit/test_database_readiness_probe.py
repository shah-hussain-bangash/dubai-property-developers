"""Readiness reports both dependencies even when the database probe fails."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from apps.api.app.api.v1.routes.health import _check_database
from apps.api.app.main import create_app


@pytest.fixture
def probes(monkeypatch):
    engine = SimpleNamespace(dispose=AsyncMock())
    state = SimpleNamespace(
        engine=engine,
        factory=Mock(return_value=engine),
        postgres=AsyncMock(return_value=True),
        redis=AsyncMock(return_value=True),
    )
    monkeypatch.setattr("apps.api.app.api.v1.routes.health.create_engine", state.factory)
    monkeypatch.setattr("apps.api.app.api.v1.routes.health.ping_database", state.postgres)
    monkeypatch.setattr("apps.api.app.api.v1.routes.health.ping_redis", state.redis)
    return state


def read_ready(settings, *, required=True):
    app = create_app(settings.model_copy(update={"readiness_checks_required": required}))
    with TestClient(app) as client:
        return client.get("/ready")


@pytest.mark.parametrize("failure", ["setup", "ping", "cleanup"])
def test_database_probe_failure_still_reports_redis(settings, probes, failure):
    failing = {
        "setup": probes.factory,
        "ping": probes.postgres,
        "cleanup": probes.engine.dispose,
    }[failure]
    failing.side_effect = OSError("fixture-private-database-error")
    response = read_ready(settings)
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"] == [
        {"name": "postgres", "status": "unavailable"},
        {"name": "redis", "status": "ok"},
    ]
    assert "fixture-private-database-error" not in response.text
    assert response.headers["X-Frame-Options"] == "DENY"
    probes.redis.assert_awaited_once()
    if failure == "setup":
        probes.engine.dispose.assert_not_awaited()
    else:
        probes.engine.dispose.assert_awaited_once()


@pytest.mark.parametrize(
    "db_ok,redis_ok", [(True, True), (True, False), (False, True), (False, False)]
)
def test_readiness_status_reflects_both_probe_results(settings, probes, db_ok, redis_ok):
    probes.postgres.return_value = db_ok
    probes.redis.return_value = redis_ok
    response = read_ready(settings)
    assert response.status_code == (200 if db_ok and redis_ok else 503)
    assert response.json()["status"] == ("ready" if db_ok and redis_ok else "not_ready")
    assert response.json()["checks"] == [
        {"name": "postgres", "status": "ok" if db_ok else "unavailable"},
        {"name": "redis", "status": "ok" if redis_ok else "unavailable"},
    ]
    probes.engine.dispose.assert_awaited_once()
    probes.redis.assert_awaited_once()


async def test_database_ping_cancellation_disposes_engine_and_propagates(settings, probes):
    probes.postgres.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await _check_database(settings)
    probes.engine.dispose.assert_awaited_once()


async def test_database_cleanup_cancellation_propagates(settings, probes):
    probes.engine.dispose.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await _check_database(settings)


def test_disabled_readiness_checks_skip_both_dependencies(settings, probes):
    response = read_ready(settings, required=False)
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"] == [
        {"name": "postgres", "status": "skipped"},
        {"name": "redis", "status": "skipped"},
    ]
    probes.factory.assert_not_called()
    probes.postgres.assert_not_awaited()
    probes.redis.assert_not_awaited()
