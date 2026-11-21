"""FastAPI application factory.

Run locally:
    uvicorn apps.api.app.main:app --reload

The application initializes the shared platform runtime on startup
and releases its resources during shutdown.

Supports both in-memory and PostgreSQL LeadStore backends through
the shared PlatformRuntime configuration.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.api.v1.router import build_v1_router
from apps.api.app.api.v1.routes import health
from apps.api.app.exception_handlers.handlers import (
    register_exception_handlers,
)
from apps.api.app.middleware.correlation import (
    CorrelationIdMiddleware,
)
from apps.api.app.middleware.error_response import ErrorResponseMiddleware
from apps.api.app.middleware.rate_limit import (
    InMemoryFixedWindowRateLimiter,
    RateLimitMiddleware,
)
from apps.api.app.middleware.security_headers import (
    SecurityHeadersMiddleware,
)
from core.config.settings import Settings, get_settings
from core.exceptions.errors import ConfigurationError
from core.observability.logging import configure_logging
from workflows.runtime import PlatformRuntime, build_runtime


def create_app(
    settings: Settings | None = None,
    runtime: PlatformRuntime | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""

    # ---------------------------------------------------------------
    # 1. Load application settings
    # ---------------------------------------------------------------

    if settings is None:
        settings = get_settings()

    # ---------------------------------------------------------------
    # 2. Validate runtime configuration
    # ---------------------------------------------------------------

    problems = settings.validate_for_runtime()

    if problems:
        raise ConfigurationError("unsafe configuration: " + "; ".join(problems))

    # ---------------------------------------------------------------
    # 3. Configure logging
    # ---------------------------------------------------------------

    configure_logging(
        settings.log_level,
        json_output=settings.log_json,
        mask_pii=settings.pii_redaction_enabled,
    )

    # ---------------------------------------------------------------
    # 4. Application startup and shutdown
    # ---------------------------------------------------------------

    @asynccontextmanager
    async def lifespan(
        app: FastAPI,
    ) -> AsyncIterator[None]:
        """Initialize and clean up the shared runtime."""

        try:
            await app.state.runtime.initialize()

            yield

        finally:
            # Always release runtime resources.
            #
            # PostgreSQL:
            #   Disposes of the SQLAlchemy connection pool.
            #
            # In-memory:
            #   Performs a safe no-op for database cleanup.
            await app.state.runtime.shutdown()

    # ---------------------------------------------------------------
    # 5. Create FastAPI application
    # ---------------------------------------------------------------

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Dubai Real Estate Multi-Agent AI Platform "
            "API (foundation). "
            "Routes tagged `development-only` are mounted "
            "only in development."
        ),
        lifespan=lifespan,
        docs_url=("/docs" if not settings.is_production else None),
        redoc_url=("/redoc" if not settings.is_production else None),
    )

    # ---------------------------------------------------------------
    # 6. Attach settings and runtime
    # ---------------------------------------------------------------

    app.state.settings = settings

    # Use the supplied runtime during tests or when injected.
    # Otherwise create a new configured runtime.
    if runtime is not None:
        app.state.runtime = runtime
    else:
        app.state.runtime = build_runtime(settings)

    # ---------------------------------------------------------------
    # 7. Register middleware
    # ---------------------------------------------------------------

    # Starlette executes the last-added middleware first:
    # correlation -> security headers -> CORS -> error response -> rate limit.

    app.add_middleware(
        RateLimitMiddleware,
        limiter=InMemoryFixedWindowRateLimiter(settings.rate_limit_per_minute),
    )

    app.add_middleware(ErrorResponseMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=[
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        ],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Correlation-ID",
        ],
        expose_headers=[
            "X-Correlation-ID",
        ],
    )

    app.add_middleware(SecurityHeadersMiddleware)

    app.add_middleware(CorrelationIdMiddleware)

    # ---------------------------------------------------------------
    # 8. Register exception handlers
    # ---------------------------------------------------------------

    register_exception_handlers(app)

    # ---------------------------------------------------------------
    # 9. Register health routes
    # ---------------------------------------------------------------

    app.include_router(health.router)

    # ---------------------------------------------------------------
    # 10. Register API v1 routes
    # ---------------------------------------------------------------

    app.include_router(build_v1_router(settings))

    return app


def _create_default_app() -> FastAPI:
    """Create the default FastAPI application for Uvicorn."""

    return create_app()


# Required by:
# uvicorn apps.api.app.main:app
app = _create_default_app()
