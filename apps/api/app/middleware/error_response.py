"""Translate unhandled request failures before outer response middleware runs."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from apps.api.app.exception_handlers.handlers import unhandled_error_handler


class ErrorResponseMiddleware(BaseHTTPMiddleware):
    """Keep structured 500 responses inside CORS and security-header middleware."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            return await unhandled_error_handler(request, exc)
