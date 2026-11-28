# Ambiguous CRM matches — local, 25 November 2026

Revision: PR #87 parent `db3d7dd840785abe1d18234935e2fcc2c71b4eb8` plus this change.
All enquiries and CRM records are fictional; verification uses the mock CRM only.

## Observed blocker

The CRM agent searched by email and phone, then selected the first returned record.
If the email matched one customer and the phone matched another, record order
determined which customer was overwritten. With CRM write approvals enabled, it
instead queued an update to that arbitrarily selected record. Duplicate email
matches produced the same problem.

## Change

The CRM agent now fails with a structured validation error when lookup returns
multiple records. It asks for match review without disclosing contacts in the error.
It does not create or update an external CRM record, append a CRM note, or queue
an approval in this case. Zero matches retain normal creation, and one matching
record retains normal updates. The existing HTTP adapter already deduplicates the
same record returned by its email and phone requests.

## Reproduction and outcomes

```powershell
python -m pytest tests/security/test_crm_ambiguous_matches.py tests/security/test_crm_record_snapshots.py tests/security/test_crm_record_id_paths.py tests/security/test_crm_account_binding.py tests/integration/test_integration_adapters.py tests/agents/test_agents.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python -m ruff check --no-cache agents/crm/agent.py tests/security/test_crm_ambiguous_matches.py
python -m ruff format --check --no-cache agents/crm/agent.py tests/security/test_crm_ambiguous_matches.py
python -m mypy --cache-dir=nul agents/crm/agent.py
```

Before the fix, five new conflict cases failed and three single-record cases passed.
After it, all eight new cases pass in a focused run of 130 tests. Conflicts are
blocked with either CRM result ordering and with approval enabled or disabled;
provider write methods are not called and stored CRM records remain unchanged.
Single email, single phone and combined matches still update the one correct record.

The full local run passes 2,070 tests, with 155 skipped, four existing expected
failures and 662 passing subtests. Ruff, formatting and the focused type check pass.

## Limits

The local enquiry is still saved before CRM lookup; the change prevents an
ambiguous external synchronization rather than rolling back local intake.
The error requires manual investigation; no new matching-review screen, automatic
merge, authoritative identity verification or CRM record-level authorization is added.
Single-field matching retains its existing semantics. No live CRM write, message,
deployment or merge is performed.
