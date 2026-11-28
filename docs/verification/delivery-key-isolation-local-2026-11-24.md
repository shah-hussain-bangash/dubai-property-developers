# Provider delivery-key isolation

Verified locally on 24 November 2026 against base application revision
`4f4b404d3762df3e12596cbeba41311dd18fa2ac` plus this PR's changes.

## Observed problem

The gateway's cache/approval keys were organization-scoped, but the WhatsApp send
tool forwarded a caller's raw event/task key to the provider client. Equal event
IDs in two organizations could therefore suppress the second delivery in the
shared mock client, even though its own approval was separate. Reusing a follow-up
task ID also suppressed a newly approved different recipient. Email passed an
empty provider key when its input did not include one. The first ten-case run had
six failures and four passing retry/compatibility controls.

## Correction

Contextual email/WhatsApp send tools now derive provider keys using the existing
canonical idempotency helper with the trusted context's organization, tool action
and full approved payload. Caller keys remain part of that payload but cannot
override the trusted namespace. The same exact scoped payload keeps its provider
key, and distinct organizations, recipients or message contents cannot reuse it.
Email context paths receive non-empty keys without an explicit caller key. Opaque
digests avoid forwarding raw conversation IDs/addresses as the delivery key.

The raw standalone tool interface retains its explicit legacy keys. Source,
conversation-consent, permission, approval and execution-window checks remain
unchanged. No provider or account configuration is changed.

## Validation and limits

All **ten delivery-key cases passed** in fixture/source-only modes. They cover
identical approved payloads in distinct organizations, non-empty scoped email
keys, separate WhatsApp deliveries, same-payload WhatsApp retry after gateway
cache loss, reused follow-up task IDs with different approved recipients, and
standalone-key compatibility. The combined delivery/source/consent/window/gateway
suite passed **88 tests**. Only mock deliveries execute.

The full local Python 3.14 suite reported **1,606 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three dependency/configuration
warnings. Expected failures concern existing recovery/fencing protocol gaps.
Ruff, formatting and strict mypy for seven email/WhatsApp source files passed.

Reproduce after installing development and document dependencies:

```text
python -m pytest tests/security/test_delivery_key_isolation.py tests/security/test_source_bound_approvals.py tests/security/test_whatsapp_optout_races.py tests/security/test_whatsapp_execution_window.py tests/unit/test_tool_gateway.py -q
python -m pytest tests -q
python -m mypy tools/whatsapp tools/email
```

Key construction is not proof that a live provider honors deduplication, and it
does not add a distributed execution ledger. The mock WhatsApp client honors
keys; the simple mock email sender still records calls without its own deduplication
cache. The gateway retains its existing cache behavior. Live providers remain
unverified/unconfigured, and no live message, merge or deployment occurred.
