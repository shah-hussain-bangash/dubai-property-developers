# Security notes

## Controls implemented in this foundation

| Control | Where |
|---|---|
| Secrets only from environment. `SecretStr` (never printed). `.env` is git-ignored | `core/config/settings.py`, `.gitignore` |
| Unsafe production config refused at startup | `Settings.validate_for_runtime()` |
| Password hashing (scrypt, per-hash parameters) for optional local auth | `core/security/passwords.py` |
| RBAC with least-privilege roles. The automation (`system`) role cannot message customers directly | `core/security/rbac.py` |
| Authentication boundary. Token mode fails closed until a verifier exists | `apps/api/app/dependencies/auth.py` |
| Tenant isolation readiness: `organization_id` FK on all tenant tables, tenant-filtered repositories, tenant-checked approvals and retrieval | `database/`, `tools/base.py`, `knowledge/` |
| Input validation (Pydantic) and sanitization (control, bidi and zero-width characters stripped) | `schemas/`, `core/security/sanitization.py` |
| Data minimization: hashed dedupe keys, redacted agent-execution summaries | `agents/lead_intake/normalization.py` |
| Secret redaction (always) and PII masking (configurable) in logs, errors and audit | `core/security/redaction.py`, `core/observability/logging.py` |
| Audit events for every side-effecting or denied tool call | `tools/base.py`, `core/events/audit.py` |
| Human approval for outbound messages and calendar writes (configurable). Execution runs as the approver | `core/policies/`, `tools/base.py` |
| Idempotency keys for external actions | `core/resilience/idempotency.py` |
| Webhook HMAC verification with timestamp tolerance and nonce replay defence. Meta `X-Hub-Signature-256` | `core/security/webhooks.py` |
| Prompt-injection boundary: untrusted data in delimited blocks, heuristics trigger escalation, permissions never prompt-controlled | `core/policies/prompt_safety.py` |
| Rate limiting (in-memory / Redis) | `apps/api/app/middleware/rate_limit.py` |
| Security headers, restrictive CORS, docs disabled in production | `apps/api/app/middleware/`, `main.py` |
| Retention policy configuration | `core/policies/retention.py` (enforcement job planned) |
| Dependency review, pip-audit, Dependabot | `.github/` |

## Generic webhook replay semantics

The generic verifier authenticates the exact `timestamp + "." + raw body` bytes. Its
nonce is a separate header and is not covered by that signature. After authentication,
the replay store therefore records both the authenticated message digest and the nonce
under separate key prefixes. Replacing a nonce or adding/removing the optional `sha256=`
signature prefix cannot make an accepted message eligible again.

Identical signed content within the replay retention period is treated as the same request,
even with a different nonce. For intentionally distinct events with otherwise identical
content, include a unique event identifier in the signed body. The signature format is
unchanged. Both replay keys expire after twice the configured timestamp tolerance plus
one second. This covers the inclusive final valid instant for future-dated requests and
keeps replay protection active when the tolerance is zero.

`InMemoryNonceStore` is a process-local development helper. Multiple workers or restarts
require a shared replay store with atomic record-if-absent and expiry semantics. The two
records are checked sequentially: a valid signature rejected for nonce reuse remains
reserved until expiry. Meta signature verification is separate and does not use this
generic replay store.

## Known gaps (must be closed before production)

- No real identity provider or token verification (OIDC/JWT).
- Approval payloads are not yet encrypted at rest (use pgcrypto or application-level encryption).
- No PostgreSQL row-level security policies yet.
- The retention/deletion job and data-subject request tooling are not implemented.
- Webhook endpoints (Meta, n8n) are not exposed yet. Verification helpers exist and are tested.
- No penetration test or threat model review has been performed.

## Secure HTTP configuration guidance

- Use TLS 1.2+ everywhere. Set HSTS at the proxy. Use HTTPS-only CORS origins in production.
- Run the API behind a reverse proxy, with `--proxy-headers` and the proxy's IPs trusted.
- Keep `/docs` disabled in production (automatic when `ENVIRONMENT=production`).
- Rotate `SECRET_KEY`, webhook secrets and provider tokens regularly. Use separate credentials per environment.

## UAE regulatory considerations (for legal review — not legal advice)

This platform **does not claim compliance with any law or certification**. Qualified UAE counsel should
review the following before processing real customer data:

- **Personal data protection:** UAE Federal Decree-Law No. 45 of 2021 (PDPL) and its executive
  regulations. If you operate from a free zone, the DIFC Data Protection Law (DIFC Law No. 5 of 2020) or
  the ADGM Data Protection Regulations 2021 may apply instead. Topics to review: lawful basis, consent
  records, data-subject rights, cross-border transfers (hosting region of cloud and LLM providers),
  breach notification and retention.
- **Real estate brokerage:** Dubai Land Department / RERA rules on broker licensing, advertising permits
  for property marketing, and accuracy of listing information. The platform's "no invented
  prices/ROI" policy and the demo-data labelling support this but don't replace it.
- **Marketing communications and telemarketing:** UAE telemarketing and unsolicited-communication
  rules (TDRA and Cabinet-level regulations), plus WhatsApp Business policies (opt-in, templates, 24h
  window). The consent flags and approval gating are in place; confirm the current rules and calling
  hours with counsel.
- **AML/CFT:** real estate brokers are designated non-financial businesses under UAE AML law. KYC and
  suspicious-transaction workflows are out of scope for this foundation.
- **AI use:** document AI-assisted customer communications in your policies. Keep humans in the loop
  for commitments, prices and contracts.
