"""OpenTelemetry-ready tracing facade.

Uses OpenTelemetry when the optional ``tracing`` extra is installed and falls back
to a no-op tracer otherwise, so business code never imports OTel directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol


class Span(Protocol):
    def set_attribute(self, key: str, value: Any) -> None: ...

    def record_exception(self, exc: BaseException) -> None: ...


class _NoopSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def record_exception(self, exc: BaseException) -> None:
        return None


class Tracer(Protocol):
    def span(self, name: str, **attributes: Any) -> Any: ...


class NoopTracer:
    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[Span]:
        yield _NoopSpan()


class OpenTelemetryTracer:
    def __init__(self, instrumentation_name: str = "dubai-real-estate-ai") -> None:
        from opentelemetry import trace

        self._tracer = trace.get_tracer(instrumentation_name)

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[Span]:
        with self._tracer.start_as_current_span(name) as span:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
            yield span


def build_tracer() -> Tracer:
    try:
        return OpenTelemetryTracer()
    except ImportError:
        return NoopTracer()
