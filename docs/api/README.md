# API overview

Interactive docs are at `http://localhost:8000/docs` (disabled when `ENVIRONMENT=production`).

## Conventions

- Versioned under `/api/v1`. Probes `/health` and `/ready` are unversioned, unauthenticated and not rate limited.
- **Correlation IDs:** send `X-Correlation-ID` (8–64 chars, `[A-Za-z0-9-_]`). It is echoed back on every
  response and included in every log line and audit event. Malformed values are replaced.
- **Errors** always use this shape:

```json
{ "error": { "code": "validation_error", "message": "...", "details": {}, "correlation_id": "..." } }
```

  Common codes: `validation_error` (422), `authentication_required` (401), `forbidden` (403),
  `not_found` (404), `conflict` (409), `rate_limited` (429), `integration_error` (502), `internal_error` (500).
- **Auth:**
  - `AUTH_MODE=dev` (dev/test only) injects a `sales_manager` principal. Override with
    `X-Dev-Roles: viewer,analyst` to test RBAC.
  - `AUTH_MODE=token` requires `Authorization: Bearer` plus a registered `TokenVerifier`. No verifier
    ships yet, so every request returns 401 (fails closed).
- **Rate limiting:** a fixed window per client IP (`RATE_LIMIT_PER_MINUTE`). The limiter is in-memory, so
  use the Redis limiter for multiple replicas. Throttled responses return 429 with the request’s
  correlation ID in the error body and a `Retry-After` header.
- **CORS:** `CORS_ALLOWED_ORIGINS` (comma-separated). Wildcards are refused outside development.
  Allowed browser origins can read the exposed `X-Correlation-ID` and `Retry-After` headers.

## Endpoints

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/health` | none | `{status, service, version, environment}` |
| GET | `/ready` | none | Dependency checks. 503 if a required dependency is down |
| GET | `/api/v1/agents` | `agents:read` | `{items: AgentDescriptor[], total}` |
| GET | `/api/v1/workflows` | `workflows:read` | `{items: WorkflowDescriptor[], total}` |
| POST | `/api/v1/leads/demo-process` | `workflows:execute` | **DEV ONLY.** Runs Lead Processing with mocks. Not mounted unless `ENABLE_DEV_ROUTES=true` in dev/test |
| GET | `/api/v1/approvals/pending` | `approvals:decide` | Pending approval requests (payload previews redacted) |
| POST | `/api/v1/approvals/{id}/decision` | `approvals:decide` | `{approve, note}`. On approve, executes the action as the approver |
| GET | `/api/v1/integrations` | `settings:admin` | Integration mode and API-access status |

## Example: demo lead

```powershell
powershell -File scripts/development/demo-lead.ps1
```

The response contains `status` (`succeeded` | `pending_approval` | `escalated` | `failed`), the step
records, the normalized lead, the qualification (score, category, factors), the routing and the mock
CRM result. `dev_only` and `uses_mock_integrations` are both `true`.
