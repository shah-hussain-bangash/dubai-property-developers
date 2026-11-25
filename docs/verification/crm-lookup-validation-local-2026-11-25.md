# CRM lookup validation — local, 25 November 2026

Repository: shah-hussain-bangash/dubai-property-developers, PR #87.
Revision: parent `48fb94fefff73ebfc9d600e854d77099fd2b32e7` plus this change.
All records and provider responses are fictional; no live CRM is contacted.

## Observed blocker

The CRM agent converted lookup IDs with str(...), so null, numeric and boolean
values could become plausible string update targets. Missing IDs and malformed
records produced internal errors. An empty object instead of the expected list
could also be interpreted as no match and lead to a new creation or approval.

## Change

The CRM agent requires lookup results to be a list, a selected record to be an
object, and its ID to satisfy the existing strict CRM record-ID validator before
any CRM write or approval. It no longer supplies a default empty list for a
missing response field or coerces provider identities into strings.

Zero valid matches still allow normal creation. One valid matching record still
allows an update; multiple matches retain the existing manual-review error.
The local enquiry remains saved before CRM lookup, as in the existing workflow.

## Reproduction and results

```powershell
python -m pytest tests/security/test_crm_lookup_record_validation.py tests/security/test_crm_readonly_identity.py tests/security/test_crm_creation_inputs.py tests/security/test_crm_ambiguous_matches.py tests/security/test_crm_record_snapshots.py tests/security/test_crm_record_id_paths.py tests/security/test_crm_account_binding.py tests/integration/test_integration_adapters.py tests/agents/test_agents.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python -m ruff check --no-cache agents/crm/agent.py tests/security/test_crm_lookup_record_validation.py
python -m ruff format --check --no-cache agents/crm/agent.py tests/security/test_crm_lookup_record_validation.py
python -m mypy --cache-dir=nul agents/crm/agent.py
```

Before the fix, the 20 new cases reported 16 failures and four passes. After it,
all 20 pass within a focused run of 192 tests. Rejected results include null,
object and string result collections, invalid record objects, missing IDs, and
null/numeric/boolean IDs. These cases make no create/update/note call and create
no pending approval, with CRM write approval enabled or disabled. Valid string
IDs, including a digits-only string, still select and update the existing record.

The full local run passes 2,132 tests, with 155 skipped, four existing expected
failures and 662 passing subtests. Ruff, formatting and the focused type check pass.

## Limits

This does not prove that a well-formed provider ID belongs to the intended person,
add authoritative source-enquiry ownership checks, or validate every provider field.
The HTTP adapter remains unverified live. No merge, website deployment or live
CRM, messaging or calendar write is performed.
