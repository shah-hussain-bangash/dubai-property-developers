# Durable agent memory and conversation consent

Local development increment on 26 November 2026, parent revision
`2979569db0ac64ca922e5f30bd03d8b11e17b670` plus this change in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
Fictional data and mock providers only; no hosted state was changed.

## Behavior and configuration

`AGENT_MEMORY_PATH` selects an optional SQLite conversation-memory adapter.
Without the setting, the existing process-local adapter remains selected. The
example environment opts in at `.data/agent-memory/memory.sqlite3`; Compose uses
`/app/agent-memory/memory.sqlite3` and shares a dedicated agent-memory-data volume
between API and worker. Images prepare that directory for the non-root user.

History and JSON conversation state survive creating a new adapter/runtime against
the same file. The existing organization/agent/conversation namespace is reused;
different identities cannot borrow the same conversation state. History preserves
append order and existing limit behavior. Read values are detached snapshots.

SQLite operations run outside the event loop in worker threads and use short-lived
connections. State patches acquire an immediate transaction before read/merge/write,
so independent connections cannot overwrite unrelated fields or erase an opt-out
through a stale read/replace cycle. Storage initializes during runtime startup;
an unusable configured path fails initialization rather than falling back to empty
memory. New database files use mode 0600; newly created directories use 0700 on Unix.
The SQLite ephemeral :memory: alias is rejected.

The WhatsApp agent and send tool share the configured adapter. A recorded opt-out
survives runtime restart and blocks a subsequent approved mock send. This remains
conversation-scoped consent, not a contact-wide registry or CRM synchronization.

## Local verification

New cases: `tests/security/test_durable_agent_memory.py`, **28 cases**.

- All 13 agent scopes retain their own history/state after adapter replacement,
  with matching IDs in two organizations and no unscoped fallback.
- Detached nested values, append ordering and history limits remain compatible.
- Thirty concurrent patches across independent adapters preserve every field and
  an existing opt-out. A separate Python process can patch the same persisted state.
- Malformed/non-object stored state fails without resetting or replacing it.
  Invalid JSON values cannot replace previous consent.
- Restarted runtime opt-out behavior, foreign-organization independence, blocked
  approved delivery, default-memory compatibility and unusable-path failure pass.
- Unix permissions are tested in Linux CI; that one case is skipped on Windows.

Focused run: **146 passed, one Unix-only skip**, one existing Starlette TestClient/
httpx warning. Full local backend: **2,235 passed, 156 skipped, four existing expected
failures, 662 passing subtests**, in 50.69 seconds with three warnings. Existing
expected failures document cross-system recovery/fencing limitations.

Ruff, formatting and focused mypy pass. Compose validates using the example
environment and a fresh Docker CLI configuration. Local Docker engine access is
unavailable; the API-container CI job now verifies opt-out persistence across two
network-disabled containers sharing a newly created disposable memory volume,
including private database-file permissions. It starts no provider delivery.

Run from the source root with the project virtual environment:

```text
python -m pytest tests/security/test_durable_agent_memory.py tests/security/test_agent_memory_isolation.py tests/security/test_whatsapp_optout_races.py tests/security/test_source_bound_approvals.py tests/security/test_explicit_delivery_consent.py tests/unit/test_core_config_and_security.py -q -p no:cacheprovider --basetemp=../fresh-durable-memory-review
python -m pytest -q -p no:cacheprovider --basetemp=../fresh-durable-memory-full
python -m ruff check database/repositories/sqlite_conversation_memory.py tests/security/test_durable_agent_memory.py core/config/settings.py workflows/runtime.py
python -m mypy database/repositories/sqlite_conversation_memory.py workflows/runtime.py core/config/settings.py
docker compose --env-file .env.example config --quiet
```

## Cutover, backup and limits

Use a private writable file and preserve it across restarts. Back it up with
SQLite's backup API or while writers are stopped. The application does not encrypt
stored text/state or enforce an automatic retention schedule. JSON-compatible
conversation state is required. This adapter is for a shared local filesystem;
multi-host/network-filesystem deployment needs a separate storage design.

Existing process memory and legacy SQL state are not migrated automatically.
Review active conversations and existing opt-outs before switching adapters;
an empty new database is not evidence of affirmative consent. The optional
PostgreSQL conversation adapter remains available separately and is not newly
wired into runtime selection by this increment.

Approvals, replay cache, audit and execution records remain process-local in the
default runtime. No scheduler, new agent tool permission, live provider, contact-wide
consent, automatic re-consent or distributed exactly-once guarantee is added.
An already in-flight provider operation cannot be recalled by this change.

No merge, deployment, existing-data migration, live message or CRM write occurred.
AWS recovery and hosted acceptance remain outstanding.
