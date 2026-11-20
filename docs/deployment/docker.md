# Docker deployment guide

## Local full stack

```powershell
Copy-Item .env.example .env
docker compose config --quiet     # validate
docker compose up --build
```

| Service | Image / build | Port (localhost only) | Notes |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | 5432 | `docker/postgres/init` enables the `vector` and `pgcrypto` extensions |
| `redis` | `redis:7-alpine` | 6379 | AOF persistence, `noeviction` |
| `migrate` | `apps/api/Dockerfile` | none | One-shot `alembic upgrade head`. The API and worker wait for it |
| `api` | `apps/api/Dockerfile` | 8000 | Non-root user, healthcheck on `/health`, `READINESS_CHECKS_REQUIRED=true` |
| `worker` | `apps/worker/Dockerfile` | none | Consumes `queue:jobs` and dead-letters failures |
| `dashboard` | `apps/dashboard/Dockerfile` | 3000 | Next.js standalone. `NEXT_PUBLIC_API_BASE_URL` is a build arg |

The dashboard image needs a committed `apps/dashboard/package-lock.json` for reproducible `npm ci`.
The reviewed lockfile is committed. Use `npm ci` for routine installs; use `npm install` only when intentionally changing dependencies.

The API image uses Python 3.15. The worker image remains on Python 3.12; both Python versions are covered by backend and integration CI. GitHub builds the API image and verifies its non-root runtime, installed dependencies and health endpoint without deploying it.

## Moving beyond local

This compose file is for development. Before running a shared or production environment:

1. Use managed PostgreSQL (with pgvector) and Redis with TLS and authentication. Do not run them from
   this compose file.
2. Inject secrets from a secret manager. Never bake them into images or `.env` files on servers.
3. Set `ENVIRONMENT=production`, `AUTH_MODE=token` (after implementing a `TokenVerifier`),
   `ENABLE_DEV_ROUTES=false` and a strong `SECRET_KEY`. The API refuses to start otherwise.
4. Terminate TLS at a reverse proxy or load balancer. Add HSTS there and run uvicorn with
   `--proxy-headers` behind trusted proxies only.
5. Run migrations as a separate release step (`alembic upgrade head`), never in app startup.
6. Configure log shipping and tracing (see `docker/monitoring/README.md`).
7. Consider hosting in a UAE region for data residency (see `docs/security/README.md`).
