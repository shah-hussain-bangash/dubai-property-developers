# In-memory audit record integrity

Verified locally on 25 November 2026 against PR #87 revision
`dbef9e72299b8dc15907ac7eeb768a1da8d88168` plus this change.

## Observed issues

The in-memory sink exposed its retained list and event models directly through
`events`. Diagnostic code could change recorded organizations, actors, outcomes,
resource IDs or nested details, and could clear/pop/append records without going
through the redacting record interface. Separately, gateway audit events used the
requested context organization. A rejected principal/context mismatch was therefore
attributed to an untrusted requested organization instead of its authenticated
actor's organization. The initial 13-case run reported ten failures and three
passing controls.

## Correction

The sink owns deep snapshots of redacted events and exposes detached list/model
snapshots for diagnostic reads. Modifying a returned view cannot update retained
history; legitimate insertion uses `record()`. IDs, timestamps, append order,
normal audit fields and existing detail redaction are preserved.

Gateway events now take `tenant_id` from the authenticated principal, matching
the already trusted actor identity. Normal matching-context events keep their
organization, while rejected cross-organization contexts cannot select the audit
owner. Authorization and tool execution rules are unchanged.

## Verification

All **13 new cases passed**: edits to five retained fields, clear/pop/append on
read views, source-model/read-view independence, redaction plus ID/time/order
preservation, denied organization attribution for two actors, and normal executed
and pending-approval tool events. The combined integrity/redaction/gateway/workflow
suite passed **45 tests**. All CRM and delivery clients in these tests are mocks.

The full local Python 3.14 suite reported **1,929 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three existing dependency or
configuration warnings. Integration skips require explicitly enabled services;
expected failures concern existing recovery/fencing gaps. Ruff, formatting and
mypy for two audit/gateway source files passed.

```text
python -m pytest tests/security/test_audit_record_integrity.py tests/security/test_frozen_set_redaction.py tests/unit/test_tool_gateway_tenant_scope.py tests/unit/test_tool_gateway.py tests/workflows/test_workflows.py -q
python -m pytest -q
python -m mypy core/events/audit.py tools/base.py
```

## Limits

The sink remains an in-memory internal helper with its existing retention behavior.
This is snapshot integrity, not persistent storage, cryptographic tamper evidence,
protection against trusted code accessing private internals, or a new public audit
API. Existing records are not rewritten or migrated. No live CRM writes, customer
messages, merge or deployment occurred.
