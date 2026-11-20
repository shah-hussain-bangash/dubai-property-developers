from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from agents.base.context import ExecutionContext
from core.config.settings import Environment, Settings
from core.security.rbac import Principal, Role
from tests.factories import TENANT
from workflows.runtime import PlatformRuntime, build_runtime


@pytest.fixture(autouse=True)
def restore_logging_configuration() -> Iterator[None]:
    """App startup replaces root handlers; keep that configuration test-local."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    try:
        yield
    finally:
        root.handlers = handlers
        root.setLevel(level)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        environment=Environment.TEST,
        log_json=False,
        rate_limit_per_minute=10_000,
        readiness_checks_required=False,
        integrations_mode="mock",
        llm_provider="mock",
        default_tenant_id=TENANT,
    )


@pytest.fixture
async def runtime(settings: Settings) -> AsyncIterator[PlatformRuntime]:
    rt = build_runtime(settings)
    await rt.initialize()
    yield rt


@pytest.fixture
def manager() -> Principal:
    return Principal(subject="manager-1", tenant_id=TENANT, roles=frozenset({Role.SALES_MANAGER}))


@pytest.fixture
def ctx(manager: Principal) -> ExecutionContext:
    return ExecutionContext(
        principal=manager, tenant_id=TENANT, correlation_id="test-correlation-0001"
    )


@pytest.fixture
def system_ctx() -> ExecutionContext:
    return ExecutionContext.system(TENANT, "test-correlation-system")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    from apps.api.app.main import create_app

    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)
