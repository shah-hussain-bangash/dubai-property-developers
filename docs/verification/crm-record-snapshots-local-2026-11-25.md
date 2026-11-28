# Mock CRM record snapshots — local, 25 November 2026

Revision: PR #87 parent `f1a520502bf83ac5066806ea5063bed033fa1a79` plus this change.
All records and callers are fictional. No live CRM or delivery service is contacted.

## Observed blocker

`MockEspoCRMClient.find_leads` returned the stored dictionaries themselves. A local
reproduction changed a search result's lastName and a subsequent get returned the
changed value without calling update. Nested values were also shared by get,
create and update. The read-only CRM tool therefore exposed a mutation path around
the normal write permission and approval checks in the default mock runtime.

## Change and reproduction

The mock CRM deep-copies lead inputs on create/update and lead outputs on get/find.
Returned records and nested values can be edited without changing stored records;
later CRM-side edits also leave earlier read results unchanged. Normal updates still
use the existing tool permissions, account binding and approval workflow.

From an installed development environment:

```powershell
python -m pytest tests/security/test_crm_record_snapshots.py tests/security/test_crm_record_id_paths.py tests/security/test_crm_account_binding.py tests/integration/test_integration_adapters.py tests/agents/test_agents.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python -m ruff check --no-cache integrations/espocrm/client.py tests/security/test_crm_record_snapshots.py
python -m ruff format --check --no-cache integrations/espocrm/client.py tests/security/test_crm_record_snapshots.py
python -m mypy --cache-dir=nul integrations/espocrm/client.py
```

All eight new cases failed before the fix. After it, the focused run passes 122
tests, including a viewer with no CRM write permission whose mutated search result
does not change the stored enquiry or its fictional consent data. Coverage includes
email and phone searches, nested get results, caller-owned create/update values,
and snapshots retained across later CRM-side edits.

The full local run passes 2,062 tests, with 155 skipped, four existing expected
failures and 662 passing subtests. It includes the recent redirect and webhook path
regressions that previously relied on CI while local execution was unavailable.
Ruff and the focused type check pass.

## Limits

This change concerns mock lead records only. The public leads dictionary remains
available to trusted fixture setup code; it is not a persistence or access-control
boundary. The HTTP adapter, live provider behavior, production data and website
deployment are unchanged. No merge or live customer communication is performed.
