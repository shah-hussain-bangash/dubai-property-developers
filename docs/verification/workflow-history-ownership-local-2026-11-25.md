# Workflow history ownership

Verified locally on 25 November 2026 against PR #87 revision
`61ca82a94490650e51ce57e7ad95a252140221e9` plus this change.

## Observed issue

The workflow runner accepted a context whose principal belonged to a different
organization. Agent checks could stop later agent steps, but state validation,
non-agent steps and workflow history creation occurred outside that boundary.
The in-memory history store retained the caller's mutable run object and exposed
the same object through its diagnostic mapping. A caller could alter stored
ownership, state or step history without saving, or reuse an execution ID to
replace another organization's record or change its workflow identity.

## Correction

The runner checks principal/context organization equality before state validation,
run construction or step execution. A mismatch raises authorization failure and
creates no history record. Matching callers retain existing workflow outcomes.

The in-memory store owns a deep snapshot on save and returns detached diagnostic
mapping/model snapshots. A retained execution ID must keep its organization and
workflow identity. Explicit same-owner/same-workflow updates remain supported.
This aligns retained-record ownership/identity behavior with existing PostgreSQL
history checks; the SQL adapter and database schema are unchanged.

## Verification

All **20 new regression cases passed**: mismatched contexts across all seven
registered workflows; a non-agent step that must never run on denial; foreign
organization and workflow-identity replacement attempts; mutable input/output
history; continued, completed, pending, escalated, domain-failed and internally
failed run outcomes; legitimate updates; bounded retention; and detached mapping
edits. The focused history/workflow/analytics suite passed **56 tests**. The initial
20-case run had 19 failures and one passing explicit-update control.

The full local Python 3.14 suite reported **1,773 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three existing dependency or
configuration warnings. Integration skips require explicitly enabled services;
expected failures concern existing recovery/fencing gaps. Ruff, formatting and
mypy for the workflow engine passed.

```text
python -m pytest tests/security/test_workflow_history_ownership.py tests/workflows/test_workflows.py tests/security/test_analytics_organization_scope.py -q
python -m pytest -q
python -m mypy workflows/engine/core.py
```

## Limits

History remains process-local and subject to the existing shared retention bound.
Ownership checks cover retained records; eviction/restart does not preserve an
ID ownership ledger. Diagnostic mappings remain an internal trusted-code interface,
not a new public history API. No durable workflow resumption, cross-process locking,
SQL migration, live CRM writes, customer messages, merge or deployment was added.
