# Roadmap and known gaps

## Done (foundation)

- Monorepo structure, packaging, lint/type/test/CI configuration.
- Shared core: config, exceptions, structured logging with redaction, tracing facade, usage/cost
  tracking, RBAC, password hashing, sanitization, webhooks, approvals, prompt-safety boundary,
  retries, idempotency, event bus, audit sink, LLM router (mock provider), conversation memory.
- 13 agents with typed contracts, allowlists and tests. The lead vertical slice is end-to-end.
- ToolGateway with approval, RBAC, idempotency and audit. 15 tools.
- 8 integration adapters (mock; HTTP for EspoCRM, Meta, n8n, Slack).
- Database schema (24 tables) + initial Alembic migration + fictional seed loader.
- RAG pipeline (in-memory store; pgvector search implemented, persisted ingestion pending).
- 6 workflows + the re-qualification sub-flow.
- FastAPI app with health, readiness, agents, workflows, approvals, integrations and the dev demo.
- Worker with a Redis queue, retries and a dead-letter queue.
- Next.js dashboard shell with labelled demo data.

## Next phase (recommended order)

1. **Persistence wiring:** DB-backed `LeadStore`, `ApprovalStore`, `AuditSink`, `WorkflowRunStore`,
   `ExecutionRecorder`. Redis idempotency and rate limiting in the runtime. `PgVectorStore.upsert`.
2. **Authentication:** OIDC/JWT `TokenVerifier`, user and role management, dashboard login.
3. **LLM provider adapter** + prompt templates + evaluation set for sales drafts (keep approval gating).
4. **Real embedding provider** + retrieval evaluation thresholds.
5. **Webhook endpoints:** Meta WhatsApp inbound (signature + parser already exist), CRM sync events.
6. **Follow-up scheduler:** periodic job that loads due tasks from the DB and enqueues `followup.scan`.
7. **Dashboard to API:** leads, approvals queue, conversations, analytics endpoints.
8. **Live integration validation** in sandbox accounts (EspoCRM, Meta).
9. **Security hardening:** RLS, payload encryption, retention job, threat model, pen test.
10. **Observability:** OTLP exporter, metrics endpoint, dashboards and alerts.

## Explicitly not implemented

- Voice/STT/telephony (interface only).
- Bayut / Property Finder live access (pending authorized API access; no scraping).
- Google Calendar live adapter.
- Opportunity management in the CRM agent.
- Generative (LLM) answers anywhere. All drafts are deterministic templates or extracted passages.
