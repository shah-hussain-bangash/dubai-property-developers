# Agent conversation-memory isolation

Verified locally on 24 November 2026 against base application revision
`4f4b404d3762df3e12596cbeba41311dd18fa2ac` plus this PR's changes.

## Observed problem

Sales Conversation and WhatsApp wrote history to the shared dependency store using
only the caller's conversation ID. WhatsApp also read opt-out state from that key.
An opt-out in one organization therefore suppressed an unrelated conversation with
the same ID in another organization. Agent histories also mixed under one ID, and
an inconsistent execution context could write memory before a tool's tenant check.

The initial 16-case run failed. Three cases reproduced these runtime failures;
13 additional cases specified the new per-agent memory-view contract.

## Correction

All agents can obtain a scoped view via `conversation_memory(ctx)`. The base agent
checks authenticated organization consistency and requires backend scope support.
Organization and agent come from trusted context/specification, never message
metadata or the conversation ID. Sales Conversation and WhatsApp now use this view.
In-memory namespaces encode the full organization/agent/conversation identity,
without delimiter ambiguity or fallback to unscoped data. Same-organization
operators retain the same agent conversation; other agents/organizations do not.

The SQL adapter supports the same views on existing conversation UUIDs. History
queries filter organization and agent ownership. Reserved ownership metadata is
assigned by the adapter, not accepted from callers. JSON state partitions retain
other agents' state under a row lock; raw state writes cannot forge or overwrite
those partitions. Unscoped SQL state requires explicit ownership review before
scoped access, preserving existing legacy data rather than assigning it silently.
No schema migration or production data write was performed.

## Validation and limits

The focused local memory/history suite passed **37 tests**, with four PostgreSQL
integration cases skipped until service-backed CI. Nineteen memory isolation cases
cover all 13 agent scopes, two organizations, opt-out isolation and persistence
within a process, histories, context mismatch, forged IDs, legacy entries,
unsupported backends and operator changes. Existing history-limit and snapshot
tests still pass. Ruff, formatting and strict mypy for 15 source files passed.

The full local Python 3.14 suite reported **1,576 passed, 153 skipped, four existing
expected failures and 662 passing subtests**. The expected failures concern existing
recovery/fencing protocol gaps. Three dependency/configuration warnings remain.
The four new PostgreSQL tests use fictional organizations/conversations in a
rolled-back transaction and exercise actual history filters, state partition
preservation, forged metadata, legacy state review and tenant/agent rebinding.

Reproduce after installing development and document dependencies:

```text
python -m pytest tests/security/test_agent_memory_isolation.py tests/unit/test_conversation_history_limits.py tests/unit/test_conversation_memory_snapshots.py -q
python -m pytest tests -q
python -m mypy core/memory agents/base agents/sales_conversation agents/whatsapp database/repositories/conversation_memory.py
```

With the repository's disposable integration database configured and
`RUN_INTEGRATION_TESTS=1`, run:

```text
python -m pytest tests/integration/test_scoped_conversation_memory.py -q
```

The default runtime remains process-local; the SQL adapter is not newly enabled by
this PR. Old unscoped memory is not automatically migrated, and durable consent
still requires its existing authoritative workflow/CRM handling. This is not
per-operator conversation access control or proof of isolation for every runtime
store. No live messages, CRM writes, merge or deployment occurred.
