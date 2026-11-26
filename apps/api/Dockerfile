# Build context: repository root.  docker build -f apps/api/Dockerfile .
FROM python:3.15-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY pyproject.toml README.md ./
COPY apps ./apps
COPY agents ./agents
COPY core ./core
COPY tools ./tools
COPY integrations ./integrations
COPY schemas ./schemas
COPY database ./database
COPY knowledge ./knowledge
COPY workflows ./workflows
RUN pip wheel --wheel-dir /wheels ".[documents]"

FROM python:3.15-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install /wheels/*.whl && rm -rf /wheels
# Alembic needs the migration scripts and config on disk.
COPY alembic.ini ./
COPY database/migrations ./database/migrations
RUN mkdir -p /app/agent-knowledge /app/agent-memory && chown app:app /app/agent-knowledge /app/agent-memory
RUN chmod 700 /app/agent-memory
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"
CMD ["uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
