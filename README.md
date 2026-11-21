# Dubai Property Developers

**Featured case study:** [Dubai Property Developers · From website enquiry to an owned client brief](docs/case-study/DUBAI_PROPERTY_DEVELOPERS_CASE_STUDY.md). A fictional property enquiry illustrates consent, assignment, and client conversion in the operations portal.

A full-stack real estate website and operations portal with a Python API, a Next.js frontend, database migrations, agent workflows and automated tests.

**Live demo:** https://dubai-property-test.duckdns.org/

## Portfolio source

This repository contains the application source, public assets, infrastructure templates and tests from the local Dubai Real Estate AI project. Server credentials, environment files, customer records, database dumps and local backups are excluded. The running demo uses its own private configuration and may differ from this source snapshot.

The project includes public property pages, enquiry handling, internal portal workflows, evidence and approval controls, and integration interfaces. Mock providers and fictional fixtures support local development; external integrations require separate configuration. A deployed demo does not imply that every provider or autonomous workflow is enabled for production use.

## Local setup and architecture

The guide below describes local setup, service boundaries and implementation limitations. Use `.env.example` to create your own local environment. Never commit real credentials or personal records. Existing source licensing is retained; no open-source license is granted by making this repository public.

---

## Platform scope

The platform combines a public property website, enquiry intake, admin and agent portals, typed agent workflows, database-backed stores and private research exports. Tool permissions, approval policies and audit records control configured integrations.

Local defaults use mock integrations, a deterministic mock LLM and fictional demo data. Optional OpenAI and local Ollama adapters and PostgreSQL lead/workflow stores are implemented, but require explicit configuration. Source availability and passing CI do not establish live provider access or production readiness. See [Implementation status](#implementation-status).

## Verified checks

[![CI](https://github.com/zenithdevelopers7-source/dubai-property-developers/actions/workflows/ci.yml/badge.svg)](https://github.com/zenithdevelopers7-source/dubai-property-developers/actions/workflows/ci.yml)

As of 20 November 2026, GitHub checks include:

- **962 backend tests** on each of Python 3.12 and 3.15, plus lint, strict type checks, migration SQL and dependency audits. Existing expected-failure safety cases remain visible in test results.
- **873 frontend tests**, TypeScript and ESLint checks, a lockfile-based installation, dependency audit and production build.
- **161 database integration tests** on each Python version against temporary PostgreSQL/Redis services, with no unexpected skips. One strict expected failure documents the PostgreSQL-to-Redis fencing publication gap.
- An actual Python 3.15 API image build, installed-dependency check, non-root runtime check and container startup/health smoke test.

Workflows use pinned action commits and read-only repository permissions; checkout credentials are not retained. Passing checks apply to this repository revision, not automatically to the separately deployed demo.

Backend coverage reporting enforces a minimum of **80% line coverage**, with two decimal places of precision. The same configured application-source scope is used on Python 3.12 and 3.15.

Each CI test job writes a summary table showing passes, skipped tests, expected failures, failures and errors. Backend summaries also show measured line coverage. Missing reports are identified explicitly; expected failures remain unresolved scenarios.

To download test evidence, open a [CI run](https://github.com/zenithdevelopers7-source/dubai-property-developers/actions/workflows/ci.yml) and use its **Artifacts** section. Backend JUnit/coverage reports and database integration reports are labelled by Python version; frontend results are in `frontend-tests`. Reports are retained for seven days and uploaded when available even if a test step fails. GitHub may require you to sign in to download them.

The [credential scan](docs/security/credential-scanning.md) checks fetched Git history with a checksum-verified scanner, narrow reviewed fixture exceptions and fully redacted findings.

## Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.12 and 3.15 tested; API image uses 3.15, FastAPI, Pydantic v2 |
| Agents / workflows | In-house typed agent framework and deterministic workflow engine |
| Data | PostgreSQL 16 + pgvector, SQLAlchemy 2.1 supported (async), Alembic |
| Cache / queue | Redis 7 |
| Dashboard | Next.js 15 (App Router), React 18, TypeScript |
| Testing tools | Vitest 5, Vite 8, Testing Library; ESLint 9 flat configuration |
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
cd apps/dashboard; npm ci; npm run dev
```

You need Python 3.12+ and Node.js 22.12+ (CI and Docker use Node.js 22). Use `npm ci` to install the reviewed dependency lockfile; run `npm audit` to check for newly reported vulnerabilities. Docker Desktop is optional and only needed for the full stack:

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
apps/dashboard    Next.js public website and admin/agent portals
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
| LLM providers | Mock by default; OpenAI Responses and local Ollama adapters require explicit configuration |
| Embeddings | Offline hashing embedder (lexical, not semantic) |
| Persistence | In-memory defaults; PostgreSQL lead and workflow stores are wired through runtime settings |
| Auth | API dev principal + RBAC; token mode requires an explicitly registered verifier and fails closed without one. Browser account/OIDC components require separate configuration |
| EspoCRM / Meta / n8n / Slack HTTP adapters | Written to public docs. **Untested against live accounts** |
| Bayut / Property Finder | Interface only, pending authorized partner API access |
| Google Calendar, Telephony | Mock only |

The [roadmap](docs/development/roadmap.md) records planned work and earlier milestones; current behavior is defined by the source and CI results.

ESLint 9 is a compatibility step for the current Next.js lint configuration and is past upstream support. ESLint 10 needs a separate framework lint-configuration migration. The documented cross-system fencing gap remains a limitation; the expected-failure tests are not a production guarantee.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md): design, layers, dependency rules
- [docs/agents/README.md](docs/agents/README.md): the 13 agents
- [docs/api/README.md](docs/api/README.md): API overview
- [docs/development/environment.md](docs/development/environment.md): environment variables
- [docs/development/workflow-validation.md](docs/development/workflow-validation.md): validate GitHub configuration before pushing
- [docs/development/windows-setup.md](docs/development/windows-setup.md): Windows local development
- [docs/deployment/docker.md](docs/deployment/docker.md): Docker deployment
- [docs/security/README.md](docs/security/README.md): security controls and UAE compliance notes
- [docs/development/integrations.md](docs/development/integrations.md): integration setup
