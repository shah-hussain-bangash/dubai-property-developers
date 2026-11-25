# CRM creation input verification — local, 25 November 2026

Repository: shah-hussain-bangash/dubai-property-developers, PR #87.
Revision: parent `69fd0ae07aac108d63a58b2ac79f6bbee0d42619` plus this change.
All records and approvals are fictional; no live CRM is contacted.

## Observed blocker

The CRM creation tool validated name/contact presence but did not validate its
local_lead_id. Missing IDs could create approval requests that could not execute;
null IDs were converted into the shared string "None" at the mock provider boundary.
Different malformed requests could therefore share a provider retry key and return
an unrelated creation result. Non-object data also produced unstructured errors.

## Change

CRM creation now requires local_lead_id to be a nonempty, non-whitespace string,
and data to be an object. The tool keeps the original string rather than coercing
other values into retry keys. Existing name/contact presence checks remain.
Validation applies before approval creation and to execution of existing approvals.

This verifies input shape, not that the named enquiry exists or belongs to the
caller. Organization account binding and the existing authorization checks still
apply. Valid source ID formats and retry-key behavior are otherwise unchanged.

## Reproduction and results

```powershell
python -m pytest tests/security/test_crm_creation_inputs.py tests/security/test_crm_ambiguous_matches.py tests/security/test_crm_record_snapshots.py tests/security/test_crm_record_id_paths.py tests/security/test_crm_account_binding.py tests/integration/test_integration_adapters.py tests/agents/test_agents.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python -m ruff check --no-cache tools/crm/tools.py tests/security/test_crm_creation_inputs.py
python -m ruff format --check --no-cache tools/crm/tools.py tests/security/test_crm_creation_inputs.py
python -m mypy --cache-dir=nul tools/crm/tools.py
```

Before the fix, 20 new rejection cases failed and one valid-flow case passed.
After the fix, all 21 cases pass within a focused run of 151 tests. Invalid IDs
are rejected with approval both enabled and disabled; no CRM record or pending
approval is created. A legacy approved null-ID request cannot execute. Valid
distinct source IDs retain distinct approved records and successful replay.

The full local run passes 2,091 tests, with 155 skipped, four existing expected
failures and 662 passing subtests. Ruff, formatting and the focused type check pass.

## Limits

The HTTP provider remains unverified live. This change does not add authoritative
source-enquiry lookup, validate all provider fields, change CRM matching semantics,
merge the PR, deploy the website or send customer communications.
