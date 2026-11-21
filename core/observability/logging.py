"""Structured JSON logging with correlation IDs and secret/PII redaction."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from core.observability.context import get_correlation_id, get_tenant_id
from core.security.redaction import redact_text, redact_value

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class RedactionFilter(logging.Filter):
    """Redacts secrets (always) and PII (configurable) from messages and extras."""

    def __init__(self, mask_pii: bool = True) -> None:
        super().__init__()
        self.mask_pii = mask_pii

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage(), mask_pii=self.mask_pii)
        record.args = None
        for key, value in list(record.__dict__.items()):
            if key in _RESERVED:
                continue
            # Identifiers are not PII; only strip secrets from them.
            mask_pii = self.mask_pii and not key.endswith("_id")
            record.__dict__[key] = redact_value({key: value}, mask_pii=mask_pii)[key]
        return True


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        record.tenant_id = get_tenant_id()
        return True


class RedactingTextFormatter(logging.Formatter):
    """Sanitize final text, including cached tracebacks and stack diagnostics."""

    def __init__(self, fmt: str, *, mask_pii: bool = True) -> None:
        super().__init__(fmt)
        self.mask_pii = mask_pii

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record), mask_pii=self.mask_pii)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(
    level: str = "INFO", *, json_output: bool = True, mask_pii: bool = True
) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(CorrelationFilter())
    handler.addFilter(RedactionFilter(mask_pii=mask_pii))
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            RedactingTextFormatter(
                "%(asctime)s %(levelname)s [%(correlation_id)s] %(name)s: %(message)s",
                mask_pii=mask_pii,
            )
        )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
