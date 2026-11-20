"""Correlation-ID propagation and structured request logging."""

from __future__ import annotations

import re
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from core.observability.context import new_correlation_id, set_correlation_id
from core.observability.logging import get_logger

HEADER = "X-Correlation-ID"
_VALID = re.compile(r"^[A-Za-z0-9\-_]{8,64}$")
logger = get_logger("api.access")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(HEADER) or request.headers.get("X-Request-ID")
        # Only accept well-formed client IDs; never log arbitrary header content.
        correlation_id = incoming if incoming and _VALID.match(incoming) else new_correlation_id()
        set_correlation_id(correlation_id)
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers[HEADER] = correlation_id
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            },
        )
        return response
