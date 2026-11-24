# Local lead data ownership

Verified locally on 24 November 2026 against PR #87 revision
`07c31592431f5f79cf8e51a1501f986dc13b6bb6` plus this change.

## Observed blocker

The duplicate-search and local-save tools trusted payload organization fields
instead of comparing them with authenticated execution context. A caller could
search a different organization's keys or save a lead under its organization.
The in-memory store also keyed records by global lead ID without checking its
existing owner. Reusing a foreign ID could overwrite that organization's record.
Its save and read methods shared mutable model objects with callers, so editing
ownership, dedupe keys or consent outside a save operation changed stored data.

## Correction

Both lead tools require trusted contextual execution and reject mismatched
principal/context/payload organizations before accessing the store. Duplicate
search uses the context's organization. Save uses a detached, validated lead
snapshot. Raw tool execution without identity now fails closed; agents retain
their existing tool allowlists and gateway execution path.

The in-memory store takes a deep snapshot on save, refuses to replace a record
owned by another organization, and returns detached snapshots from list/search.
Updating a returned model requires an explicit save. This matches the existing
PostgreSQL store's record-ownership rule; no database migration or SQL adapter
implementation changed.

## Verification

All **12 new regression cases passed**: spoofed read/write organization fields,
direct calls without identity, mismatched principals, reused foreign lead IDs,
mutation after save and after both read methods, independent normal operations
in two organizations, and a CRM-agent foreign-lead rejection before either local
or external writes. The combined lead/CRM/gateway scope checks passed **44 tests**.

The full local Python 3.14 suite passed **1,696 tests**, with **155 skips**, **four
existing expected failures**, **662 passing subtests** and three existing
dependency/configuration warnings. Skips require explicitly enabled integration
services; expected failures cover existing recovery/fencing gaps. Ruff, formatting
and mypy for three search source files passed.

```text
python -m pytest tests/security/test_lead_data_ownership.py tests/security/test_crm_account_binding.py tests/unit/test_tool_gateway_tenant_scope.py -q
python -m pytest -q
python -m mypy tools/search
```

## Limits

New regression evidence uses the local in-memory lead store and mock CRM. The
shared tool checks apply to either configured store, but no new live database or
CRM verification was performed locally. In-memory storage remains process-local;
this does not add durable consent tracking, CRM account routing, cross-process
transactions or data migration. No live CRM writes, customer messages, merge or
deployment occurred.
