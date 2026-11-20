# Dubai Property Developers

A full-stack real estate website and operations portal with a Python API, a Next.js frontend, database migrations, agent workflows and automated tests.

**Live demo:** https://dubai-property-test.duckdns.org/

## Portfolio source

This repository contains the application source, public assets, infrastructure templates and tests from the local Dubai Real Estate AI project. Server credentials, environment files, customer records, database dumps and local backups are excluded. The running demo uses its own private configuration and may differ from this source snapshot.

The project includes public property pages, enquiry handling, internal portal workflows, evidence and approval controls, and integration interfaces. Mock providers and fictional fixtures support local development; external integrations require separate configuration. A deployed demo does not imply that every provider or autonomous workflow is enabled for production use.

## Local setup and architecture

The original developer guide follows, including setup, service boundaries and implementation limitations. Use `.env.example` to create your own local environment. Never commit real credentials or personal records. Existing source licensing is retained; no open-source license is granted by making this repository public.

---

# Dubai Real Estate AI Platform

A modular monorepo foundation for a multi-agent AI platform that supports a Dubai real estate brokerage.
It covers lead intake and qualification, property recommendation, sales conversations, follow-ups,
CRM sync and knowledge-based support. Every action that reaches a live system is approval-gated and audited.

> **Status: foundation / vertical slice.** Everything runs locally against **mock integrations,
> a deterministic mock LLM and fictional demo data**. Nothing connects to live CRM, WhatsApp, email
> or telephony accounts. See [Implementation status](#implementation-status).

## Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.12, FastAPI, Pydantic v2 |
| Agents / workflows | In-house typed agent framework and deterministic workflow engine |
| Data | PostgreSQL 16 + pgvector, SQLAlchemy 2.x (async), Alembic |
| Cache / queue | Redis 7 |
| Dashboard | Next.js 14 (App Router) + TypeScript |
| Ops | Docker Compose, GitHub Actions |

## Quick start (Windows)

```powershell
# 1. Backend: creates .venv, installs deps, copies .env.example -> .env
powershell -ExecutionPolicy Bypass -File scripts/setup/setup-windows.ps1

# 2. Tests
.\.venv\Scripts\python -m pytest

# 3. API  ->  http://localhost:8000/docs
.\.venv\Scripts\python -m uvicorn apps.api.app.main:app --reload --port 8000

# 4. Try the end-to-end demo (fictional lead, mock CRM)
powershell -File scripts/development/demo-lead.ps1

# 5. Dashboard  ->  http://localhost:3000
cd apps/dashboard; npm install; npm run dev
```

You need Python 3.12+ and Node.js 20 LTS. Docker Desktop is optional and only needed for the full stack:

```powershell
Copy-Item .env.example .env
docker compose up --build      # postgres+pgvector, redis, migrate, api, worker, dashboard
```

The API works without PostgreSQL or Redis: the agent runtime uses in-memory stores, and `/ready` reports
`degraded`. The database is needed for migrations, seeding and the integration tests.

## Key endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness (DB/Redis checks when `READINESS_CHECKS_REQUIRED=true`) |
| GET | `/api/v1/agents` | All 13 agents with implementation status |
| GET | `/api/v1/workflows` | Workflow definitions |
| POST | `/api/v1/leads/demo-process` | **Development only.** Runs the lead workflow with mocks |
| GET | `/api/v1/approvals/pending` | Human-in-the-loop queue |
| POST | `/api/v1/approvals/{id}/decision` | Approve or reject, then execute as the approver |
| GET | `/api/v1/integrations` | Integration mode and API-access status |

## Repository layout

```text
apps/api          FastAPI app (routes, middleware, auth deps, error handlers)
apps/worker       Redis-queue background worker
apps/dashboard    Next.js dashboard (demo data clearly labelled)
agents/           13 agents + base contracts + registry
core/             config, llm, memory, policies, security, observability, exceptions, events, resilience, cache
tools/            permission-gated tools (CRM, WhatsApp, email, calendar, property, documents, search, analytics)
integrations/     adapters: EspoCRM, Meta WhatsApp, Google, Bayut, Property Finder, telephony, n8n, Slack
schemas/          shared Pydantic contracts
database/         SQLAlchemy models, Alembic migrations, repositories, seeds, sessions
knowledge/        RAG: ingestion, chunking, embeddings, vector stores, retrieval, evaluation
workflows/        workflow engine + 6 business workflows + runtime composition root
tests/            unit, integration, agents, workflows, security, evaluations
docs/             architecture, api, agents, deployment, security, development
```

## Implementation status

| Area | Status |
|---|---|
| Lead Processing workflow (intake → dedupe → qualify → route → CRM) | **Functional** (mock CRM) |
| Property Recommendation workflow | **Functional** (fictional catalog) |
| Supervisor, Lead Intake, Qualification, Property Recommendation, CRM agents | **Functional**, deterministic |
| Sales Conversation, Follow-Up, Email, WhatsApp, Marketing, Documents, Analytics agents | **Partial** (rules and templates; LLM drafting pending) |
| Voice agent | **Interface only** (no STT or telephony provider) |
| Sales, Follow-Up, CRM Sync, Knowledge Support workflows | **Partial** |
| LLM providers | Mock only. Real adapters not implemented |
| Embeddings | Offline hashing embedder (lexical, not semantic) |
| Persistence | Schema + migration done. Runtime stores are still in-memory (DB wiring pending) |
| Auth | Dev principal + RBAC. Token/OIDC verification **not implemented** (fails closed) |
| EspoCRM / Meta / n8n / Slack HTTP adapters | Written to public docs. **Untested against live accounts** |
| Bayut / Property Finder | Interface only, pending authorized partner API access |
| Google Calendar, Telephony | Mock only |

The full list is in [docs/development/roadmap.md](docs/development/roadmap.md).

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md): design, layers, dependency rules
- [docs/agents/README.md](docs/agents/README.md): the 13 agents
- [docs/api/README.md](docs/api/README.md): API overview
- [docs/development/environment.md](docs/development/environment.md): environment variables
- [docs/development/windows-setup.md](docs/development/windows-setup.md): Windows local development
- [docs/deployment/docker.md](docs/deployment/docker.md): Docker deployment
- [docs/security/README.md](docs/security/README.md): security controls and UAE compliance notes
- [docs/development/integrations.md](docs/development/integrations.md): integration setup
