# CRM record identity verification — local, 25 November 2026

Repository: shah-hussain-bangash/dubai-property-developers, PR #87.
Revision: parent `77d6f0c7e7895b8f5989f75dbb52a05ae85c24b8` plus this change.
All records, credentials and approvals are fictional; HTTP tests use MockTransport.

## Observed blocker

The mock CRM accepted an id inside create/update field dictionaries. A local
update to mock-lead-00001 with id=fictional-other-record left the storage key
unchanged but changed the returned record identity. Later contact lookup could
then select an unrelated or nonexistent record ID. Create fields could likewise
override the generated record identity. These fields also reached HTTP requests.

## Change

The platform's CRM adapter contract now treats the top-level id field as read-only
in lead creation and updates, even when its supplied value equals the target ID
or is null. Update targets continue to use external_id. Shared validation runs
in both tools before approval and inside both mock and HTTP adapters before mutation,
retry-cache lookup or transport. Update field dictionaries must also be objects.

This is an application restriction, not a claim about every provider API's optional
support for client-supplied IDs. Other provider fields retain their existing behavior.

## Reproduction and outcomes

```powershell
python -m pytest tests/security/test_crm_readonly_identity.py tests/security/test_crm_creation_inputs.py tests/security/test_crm_ambiguous_matches.py tests/security/test_crm_record_snapshots.py tests/security/test_crm_record_id_paths.py tests/security/test_crm_account_binding.py tests/integration/test_integration_adapters.py tests/agents/test_agents.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python -m ruff check --no-cache integrations/espocrm/client.py tools/crm/tools.py tests/security/test_crm_readonly_identity.py
python -m ruff format --check --no-cache integrations/espocrm/client.py tools/crm/tools.py tests/security/test_crm_readonly_identity.py
python -m mypy --cache-dir=nul integrations/espocrm/client.py tools/crm/tools.py
```

Before the fix, 20 new rejection cases failed and one normal update passed.
After the fix, all 21 pass within a focused run of 172 tests. Rejected changes
leave the mock store unchanged, create no pending approval and make no HTTP call.
A legacy approved identity change is rejected at execution. A normal approved
field update retains the original record ID.

The full local run passes 2,112 tests, with 155 skipped, four existing expected
failures and 662 passing subtests. Ruff, formatting and focused type checks pass.

## Limits

This does not establish CRM record ownership or restrict reassignment fields.
The HTTP adapter is still unverified live. No merge, website deployment or live
CRM, messaging or calendar write is performed.
