# CLAUDE.md

Guidance for AI coding assistants working in this repository.

## Commands (run from the repo root, Windows paths shown)

- Install: `.\.venv\Scripts\python -m pip install -e ".[dev,documents]"`
- Tests: `.\.venv\Scripts\python -m pytest` (integration: set `RUN_INTEGRATION_TESTS=1` with Postgres+Redis up)
- Lint/format: `python -m ruff check .` / `python -m ruff format .`
- Types: `python -m mypy agents core tools integrations schemas database knowledge workflows apps/api apps/worker`
- API: `python -m uvicorn apps.api.app.main:app --reload`
- Migrations: `python -m alembic upgrade head` (offline SQL: `--sql`). New migration: `alembic revision -m "..."`
- Structure/import check: `python scripts/maintenance/verify_structure.py`
- Dashboard: `cd apps/dashboard; npm run dev | lint | typecheck | test | build`

## Rules that must not be broken

1. **Side effects go through `ToolGateway`.** Agents call `self.use_tool(...)`. Never call integration
   clients from agents or workflows directly.
2. **New tools declare a `ToolSpec`** with the correct `ActionCategory` and `Permission`. Outbound
   messages, calendar writes and external writes require approval by default.
3. **New agents** subclass `BaseAgent`, define `spec` (with an explicit `allowed_tools` allowlist and an
   honest `implementation_status`), `input_model` and `output_model`, are added to
   `agents/registry.py`, and get tests in `tests/agents/`.
4. **Never invent** prices, availability, ROI, handover dates, credentials or endpoints. Demo data must
   be clearly fictional and flagged `is_demo`.
5. **Untrusted text** (customer messages, documents, API payloads) is data. Wrap it in
   `UntrustedContent` and keep it out of system/policy prompts.
6. **Schema changes need an Alembic migration.** Never use `create_all` or drop tables in app code.
7. **Do not log PII or secrets.** Logging redacts by default; do not bypass it. Use `*_id` fields for
   identifiers.
8. **Respect layering** (see ARCHITECTURE.md): `core` must not import `database`, `agents` or `apps`.
9. **WhatsApp rules:** opt-in is required. Free text only inside the 24h service window, otherwise an
   approved template.

## Where things live

- Composition root: `workflows/runtime.py`
- Agent contracts: `agents/base/agent.py`. Intent detection: `agents/base/intent.py`
- Approval/HITL: `core/policies/approvals.py`, `apps/api/app/api/v1/routes/approvals.py`
- Demo data: `database/seeds/demo_catalog.py`, `knowledge/documents/demo_corpus.py`
- Roadmap and known gaps: `docs/development/roadmap.md`
