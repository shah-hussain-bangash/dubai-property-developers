# Automation webhook path verification — 25 November 2026

Revision: PR #87 parent `28018399e0a7c1d702f3b32f12fd88b305c14fdf` plus this change.
Provider verification is mock-only; no automation server is contacted.

## Observed issue

Source review found that HttpN8nClient inserted an arbitrary webhook_path into
`/webhook/{path}`. Dot segments such as `../rest/settings` could escape the webhook
prefix during URL normalization. Query and fragment characters could also change
the requested route. The same-origin guard does not constrain paths on that origin.

## Change

Both the HTTP and mock adapters validate webhook paths before triggering anything.
The explicit adapter contract accepts a maximum of 1,024 input characters, made of
nonempty ASCII letter/digit/underscore/hyphen/dot segments. Individual dot and
double-dot segments, encoded characters, URL controls and empty internal segments
are rejected. Existing outer slash trimming and ordinary nested paths remain supported.
This conservative contract does not claim to support every possible n8n custom path.

The mock now records the same normalized path that the HTTP adapter requests.

## Reproduction

Using an installed development environment:

```powershell
python -m pytest tests/security/test_n8n_webhook_paths.py tests/integration/test_integration_adapters.py tests/unit/test_integration_origin_boundary.py tests/security/test_integration_redirect_rejection.py -q -p no:cacheprovider
python -m ruff check --no-cache integrations/n8n/client.py tests/security/test_n8n_webhook_paths.py
python -m ruff format --check --no-cache integrations/n8n/client.py tests/security/test_n8n_webhook_paths.py
python -m mypy --cache-dir=nul integrations/n8n/client.py
```

The 47 new cases cover rejected path traversal, query/fragment injection, encoded
and control characters, non-string/empty/overlength inputs, and valid nested paths.
They assert that invalid HTTP calls never reach the mock transport, invalid mock
calls create no trigger record, and valid calls retain the payload, idempotency header
and configured base prefix.

Local commands stalled after the previous disk-full incident, so this revision uses
GitHub CI for execution, formatting and type-check verification. No local pass count
is claimed for this change. The prior redirect fix is retained.

## Limits

Path validation is not workflow-level authorization. This change does not add a
workflow allowlist, live n8n credentials or exactly-once execution. It does not merge
the PR, deploy the website or send customer messages.
