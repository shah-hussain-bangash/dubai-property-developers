# Environment configuration

Settings are loaded by `core/config/settings.py` (Pydantic Settings) from environment variables and an
optional `.env` file, which is git-ignored. `.env.example` documents every variable. Names are
case-insensitive. Lists are comma-separated.

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` / `test` / `staging` / `production` |
| `LOG_LEVEL`, `LOG_JSON` | `INFO`, `true` | Structured JSON logs to stdout |
| `DEFAULT_TENANT_ID` | `demo-org` | Tenant used by the dev principal and demo data |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated. No wildcard outside dev |
| `ENABLE_DEV_ROUTES` | `true` | Mounts `/api/v1/leads/demo-process` (dev/test only) |
| `RATE_LIMIT_PER_MINUTE` | `120` | Positive requests per client IP; zero and negative values are rejected |
| `AUTH_MODE` | `dev` | `dev` (dev/test only) or `token` |
| `SECRET_KEY` | placeholder | **Must be changed** outside dev (startup refuses the placeholder) |
| `WEBHOOK_SIGNING_SECRET`, `WEBHOOK_TOLERANCE_SECONDS` | unset, `300` | HMAC webhook verification and replay window |
| `PII_REDACTION_ENABLED` | `true` | Masks emails and phone numbers in logs (secrets are always redacted) |
| `DATABASE_URL` | local Docker URL | `postgresql+asyncpg://...` |
| `REDIS_URL` | `redis://localhost:6379/0` | |
| `READINESS_CHECKS_REQUIRED` | `false` | When `true`, `/ready` pings Postgres and Redis and returns 503 on failure |
| `READINESS_PROBE_TIMEOUT_SECONDS` | `3` | Per-dependency timeout in seconds; greater than 0 and at most 30 |
| `LLM_PROVIDER`, `LLM_PRIMARY_MODEL`, `LLM_FALLBACK_MODELS` | `mock` | Only `mock` has an adapter today |
| `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` | `30`, `2` | |
| `EMBEDDING_PROVIDER`, `EMBEDDING_DIMENSION` | `hashing`, `1536` | The dimension must match the migration |
| `KNOWLEDGE_CHUNK_SIZE`, `KNOWLEDGE_CHUNK_OVERLAP` | `800`, `120` | Characters |
| `KNOWLEDGE_STALE_AFTER_DAYS` | `180` | Reserved for the staleness policy (currently driven by each document's `review_by`) |
| `AGENT_DEFAULT_TIMEOUT_SECONDS` | `20` | Per-agent override via `AgentConfig` |
| `APPROVAL_REQUIRED_FOR_OUTBOUND_MESSAGES` | `true` | WhatsApp, email |
| `APPROVAL_REQUIRED_FOR_CRM_WRITES` | `false` | |
| `APPROVAL_REQUIRED_FOR_CALENDAR_EVENTS` | `true` | |
| `DATA_RETENTION_DAYS_CONVERSATIONS`, `DATA_RETENTION_DAYS_AUDIT_LOGS` | `365`, `2555` | Policy values. The enforcement job is planned |
| `INTEGRATIONS_MODE` | `mock` | `live` enables only the integrations whose credentials are set |
| `ESPOCRM_BASE_URL`, `ESPOCRM_API_KEY` | unset | |
| `META_WHATSAPP_PHONE_NUMBER_ID`, `META_WHATSAPP_ACCESS_TOKEN`, `META_APP_SECRET`, `META_GRAPH_API_VERSION` | unset, `v20.0` | |
| `GOOGLE_CREDENTIALS_FILE`, `TELEPHONY_PROVIDER` | unset | Mock only for now |
| `N8N_WEBHOOK_BASE_URL`, `SLACK_WEBHOOK_URL` | unset | |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Dashboard. Fixed at build time |

## Readiness probe timing

Each required dependency probe has its own timeout. A timed-out probe reports `unavailable`,
and `/ready` returns 503 while still reporting the other dependency. Checks run sequentially,
so allow for both budgets when setting an external readiness-check timeout. Cancellation is
cooperative: probe cleanup is attempted, and cleanup that delays cancellation can extend the
elapsed request time. Caller cancellation continues to propagate. Disabled checks perform no
probe work and retain the existing `degraded` response.

## Production safety checks

`Settings.validate_for_runtime()` runs when the API starts. Outside development/test the API **refuses
to start** if any of the following holds:

- `AUTH_MODE=dev`
- dev routes are enabled
- `SECRET_KEY` is the placeholder
- CORS contains `*`
