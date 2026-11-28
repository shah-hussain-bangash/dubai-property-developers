# CRM record path verification — local, 25 November 2026

Revision: PR #87 parent `7f0e9be6595c7ae177c14e1958d39172f7e51a74` plus this change.
All enquiries, approvals and credentials in this verification are fictional.
HTTP requests use `httpx.MockTransport`; no live CRM or other delivery service is contacted.

## Observed blocker

The HTTP adapter interpolated unvalidated record IDs into `/Lead/{id}`.
A local mocked read with `../User/fictional` produced the URL
`https://crm.example.test/api/v1/User/fictional`. The existing same-origin guard
allowed it because the origin had not changed. An update used the same unsafe construction.

Before the fix, the initial regression suite reported 56 failures and four passes.
The failures covered missing rejection of path, query, fragment, encoding, control,
non-string and overlength inputs, mock adapter inconsistency, and unsafe approval creation.

## Change and reproduction

Both CRM adapters now reject read/update IDs outside `[A-Za-z0-9_-]{1,128}`.
The update tool applies the same check before approval creation and when executing
an existing approval. This is an explicit conservative application contract; provider
formats outside it require an intentional compatibility change rather than silent rewriting.

From the repository, using an installed development environment:

```powershell
python -m pytest tests/security/test_crm_record_id_paths.py tests/security/test_crm_account_binding.py tests/integration/test_integration_adapters.py tests/agents/test_agents.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python -m ruff check integrations/espocrm/client.py tools/crm/tools.py tests/security/test_crm_record_id_paths.py
python -m ruff format --check integrations/espocrm/client.py tools/crm/tools.py tests/security/test_crm_record_id_paths.py
python -m mypy integrations/espocrm/client.py tools/crm/tools.py
```

The focused run passes 114 tests, including 62 new regression cases. Unsafe HTTP
calls never reach the mock transport, unsafe updates create no pending approval,
and a previously approved unsafe update cannot reach the provider. Valid IDs retain
the exact Lead route, and a fictional lead update still completes after human approval.

The full local run passes 1,991 tests, with 155 skipped and four existing expected failures.
Ruff and the focused type check pass. Local integration skips do not verify live services.

## Limits

This change does not prove record ownership inside the bound CRM account, validate
all CRM payload fields, or change note parent IDs (which are sent in JSON, not URL paths).
It does not contact EspoCRM, merge the PR, deploy the website or send customer messages.
