# Monitoring (planned)

Not yet part of `docker-compose.yml`. The code is ready for it:

- **Tracing:** install the `tracing` extra (`pip install -e .[tracing]`). `core/observability/tracing.py` then uses
  OpenTelemetry automatically. Add an OTLP exporter and a collector (for example the
  OpenTelemetry Collector with Jaeger or Tempo).
- **Logs:** every service writes JSON lines to stdout. Each line carries `correlation_id` and `tenant_id`,
  and secrets and PII are redacted. You can ship them with Loki/Promtail or another log collector.
- **Metrics:** a Prometheus `/metrics` endpoint is planned. Token usage and cost already go through
  `core/observability/usage.py`.

`otel-collector.example.yaml` is a starting point for a local OpenTelemetry Collector.
