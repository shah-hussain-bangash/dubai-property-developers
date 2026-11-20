"""Live PostgreSQL/Redis checks. Skipped unless RUN_INTEGRATION_TESTS=1 (e.g. in docker compose)."""

from __future__ import annotations

import pytest

from core.cache.redis import ping_redis
from core.config.settings import get_settings
from database.sessions.engine import create_engine, ping_database
from tests.factories import integration_enabled

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not integration_enabled(), reason="set RUN_INTEGRATION_TESTS=1 with services running"
    ),
]


async def test_postgres_reachable() -> None:
    engine = create_engine(get_settings())
    try:
        assert await ping_database(engine)
    finally:
        await engine.dispose()


async def test_redis_reachable() -> None:
    assert await ping_redis(get_settings())
