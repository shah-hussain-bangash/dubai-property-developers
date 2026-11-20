# Architecture

## Goals

1. **Safe by construction.** Permissions, approvals and policies are enforced in code (the ToolGateway),
   never by prompts.
2. **Modular.** Each concern lives in one layer. Agents contain business decisions, tools contain side
   effects, integrations contain provider protocols.
3. **Honest.** Mock, demo and unimplemented capabilities are labelled in code, in the API and in the UI.
4. **Replaceable.** Providers (LLM, embeddings, CRM, vector store, queues) sit behind protocols.

## Layers and dependency rules

```text
apps/api, apps/worker          (delivery: HTTP, queue)
        │
workflows/                     (engine + business workflows + runtime composition root)
        │
agents/                        (13 agents, BaseAgent, registry)
        │
knowledge/   tools/            (RAG pipeline; permission-gated tools)
        │      │
integrations/                  (provider adapters: protocol + mock + http)
        │
database/                      (models, migrations, repositories)
        │
core/                          (config, security, policies, observability, llm, memory, events, resilience)
        │
schemas/                       (shared Pydantic contracts)
```

A layer may import only from the layers below it. `core` never imports `database`, `agents` or `apps`.
The database-backed `ConversationMemory` therefore lives in `database/repositories/`.

## Request flow: lead processing (the working vertical slice)

```text
POST /api/v1/leads/demo-process  (dev only)
  └─ WorkflowRunner.run(LEAD_PROCESSING)
       1. lead_intake agent   validate → normalize (E.164, email, locations) → dedupe (hashed keys)
       2. duplicate_gate      duplicates stop here (no CRM write)
       3. qualification agent rules-v1 score with explained factors → category
       4. route               queue/priority from category (rent → leasing)
       5. crm agent           leads.save → crm.find_leads → crm.create_lead|update_lead → crm.add_note
                              (every call goes through ToolGateway: allowlist → validate → idempotency
                               → approval policy → RBAC → execute → audit)
```

## Key components

| Component | Location | Responsibility |
|---|---|---|
| `Settings` | `core/config/settings.py` | Env config. `validate_for_runtime()` refuses unsafe production setups |
| `BaseAgent` | `agents/base/agent.py` | Validation, timeout, tracing, logging, error mapping and execution records for every agent |
| `AgentSpec` | same | Agent id, responsibilities, implementation status, **explicit tool allowlist** |
| `ToolGateway` | `tools/base.py` | The only path to side effects: allowlist, validation, idempotency, approval, RBAC, audit |
| `ApprovalPolicy` | `core/policies/actions.py` | Which action categories need human approval (configurable) |
| `ApprovalStore` | `core/policies/approvals.py` | Human-in-the-loop requests. Approved actions run *as the approver* |
| `ModelRouter` | `core/llm/router.py` | Provider-agnostic LLM calls with retries, fallbacks and token/cost tracking |
| Prompt boundary | `core/policies/prompt_safety.py`, `core/llm/prompts.py` | Untrusted content is delimited data in a separate message; injection heuristics flag escalation |
| `WorkflowRunner` | `workflows/engine/core.py` | Typed state, step records, terminal outcomes (complete / pending approval / escalate / failed) |
| `PlatformRuntime` | `workflows/runtime.py` | Composition root shared by the API and the worker |
| RAG | `knowledge/` | Ingest → normalize → chunk → embed → store, with versioning, staleness, ACL filters and citations |

## Multi-tenancy

Every tenant-owned table has `organization_id` (FK to `organizations`), and `TenantRepository` filters
every query by it. Approvals, retrieval filters, lead dedupe and audit events all carry `tenant_id`.
Row-level security in PostgreSQL is recommended before onboarding a second organization.

## Why not LangGraph (yet)?

The workflows are deterministic business processes. The engine is about 200 lines with no framework
lock-in, and each step is a plain async function over a Pydantic state. If LLM-driven branching
becomes necessary, the same step functions can be wrapped as LangGraph nodes without changing
business logic.

## Persistence status

The schema (24 tables) and the initial Alembic migration are complete. The runtime currently wires
**in-memory** stores (leads, approvals, idempotency, audit, vectors, memory) behind protocols. The
Postgres and Redis implementations of those protocols are the next phase (see the roadmap). Some
already exist: `SqlConversationMemory`, `PgVectorStore.search`, `RedisIdempotencyStore`,
`RedisFixedWindowRateLimiter`.

## Assumptions

- The reference image mentioned in the brief was not available. The layout follows the textual tree
  in the brief.
- A single `pyproject.toml` installs all backend packages (setuptools `packages.find`) in editable mode.
  The top-level packages (`core`, `tools`, `schemas`, ...) are installed as-is. Rename them under a
  namespace (for example `dubai_ai.*`) if they collide with other packages in your environment.
- The embedding dimension is fixed at 1536 in the migration. Changing it requires a new migration and
  re-embedding.
- The default timezone is Asia/Dubai. All timestamps are stored in UTC.
