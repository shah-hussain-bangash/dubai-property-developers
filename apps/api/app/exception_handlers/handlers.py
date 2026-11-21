"""Structured error responses: ``{"error": {code, message, details, correlation_id}}``."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.exceptions.errors import PlatformError
from core.observability.context import get_correlation_id
from core.observability.logging import get_logger

logger = get_logger("api.errors")


def _body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "correlation_id": get_correlation_id(),
        }
    }


async def platform_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, PlatformError)
    message, details = exc.message, exc.details
    if exc.status_code >= 500:
        logger.warning("platform error", extra={"error_code": exc.code})
        message, details = "An unexpected error occurred", {}
    return JSONResponse(status_code=exc.status_code, content=_body(exc.code, message, details))


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_body("validation_error", "Request validation failed", {"errors": errors}),
    )


async def http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    message = "An unexpected error occurred" if exc.status_code >= 500 else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=_body(f"http_{exc.status_code}", message),
        headers=getattr(exc, "headers", None),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error")
    return JSONResponse(
        status_code=500, content=_body("internal_error", "An unexpected error occurred")
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PlatformError, platform_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
