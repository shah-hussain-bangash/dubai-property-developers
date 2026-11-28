# Mock CRM creation retry conflicts — local, 25 November 2026

Repository: shah-hussain-bangash/dubai-property-developers, PR #87.
Revision: parent `72e45311dc5a358ff74269a8cc7f8387144986da` plus this change.
All enquiries, approvals and CRM records are fictional. No live CRM is contacted.

## Observed blocker

The mock CRM returned its cached creation ID whenever a retry key matched, without
checking the request fields. Changed contact details under the same source enquiry
ID could therefore be reported as successfully created while the CRM retained the
old data. A second, distinct human approval did not prevent this false acknowledgement.

## Change

The mock keeps a SHA-256 fingerprint of the canonical JSON of the original creation
request. Reusing its key with different creation fields raises a structured conflict
without changing the existing record or replacing the original receipt. Equivalent
dictionary order is accepted; JSON booleans and numbers remain distinct. The mock
rejects non-serializable/non-finite creation fields before reserving any retry key.

The receipt describes the original creation request, not the current record. Later
ordinary updates do not prevent an identical retry of the original creation.
Valid source IDs and gateway approval/cache keys are unchanged.

## Reproduction and outcomes

```powershell
python -m pytest tests/security/test_crm_creation_retry_conflicts.py tests/security/test_crm_lookup_record_validation.py tests/security/test_crm_readonly_identity.py tests/security/test_crm_creation_inputs.py tests/security/test_crm_ambiguous_matches.py tests/security/test_crm_record_snapshots.py tests/security/test_crm_record_id_paths.py tests/security/test_crm_account_binding.py tests/integration/test_integration_adapters.py tests/agents/test_agents.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python -m ruff check --no-cache integrations/espocrm/client.py tests/security/test_crm_creation_retry_conflicts.py
python -m ruff format --check --no-cache integrations/espocrm/client.py tests/security/test_crm_creation_retry_conflicts.py
python -m mypy --cache-dir=nul integrations/espocrm/client.py
```

Before the fix, eight new cases failed and two valid retry cases passed. After it,
all ten pass within a focused run of 202 tests. Coverage includes changed names,
contacts and nested values, newly approved conflicting requests, an agent retry
with changed contacts, reordered dictionaries, later updates and invalid JSON.

The full local run passes 2,142 tests, with 155 skipped, four existing expected
failures and 662 passing subtests. Ruff, formatting and the focused type check pass.

## Limits

This applies to the process-local mock only. The HTTP adapter and the live provider's
retry behavior are unchanged and unverified. This does not add durable receipts,
distributed exactly-once behavior, or an automatic conflict-resolution workflow.
The local enquiry may already have been saved when synchronization reports a
conflict. No merge, website deployment or real customer communication is performed.
