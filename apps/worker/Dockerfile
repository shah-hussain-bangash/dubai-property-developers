# Build context: repository root.  docker build -f apps/worker/Dockerfile .
FROM python:3.12-slim AS builder
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

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install /wheels/*.whl && rm -rf /wheels
USER app
CMD ["python", "-m", "apps.worker.main"]
