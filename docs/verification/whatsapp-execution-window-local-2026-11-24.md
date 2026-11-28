# WhatsApp execution-window revalidation

Verified locally on 24 November 2026 against base application revision
`4f4b404d3762df3e12596cbeba41311dd18fa2ac` plus this PR's changes.

## Observed gap and correction

Send validation ran before acquiring the execution lock. If the customer-service
window expired during that wait, an already approved message could still reach
the mock provider. Asynchronous source verification introduced another interval
between initial validation and provider execution. Direct legacy tool execution
also lacked its own service-window check.

The WhatsApp tool now calls its validator again at the shared private send
boundary, immediately before calling the provider. Both normal invocation and
approval execution therefore recheck after waits and source verification. This
retains the existing validation, source, permission and approval requirements.
An expired/missing/future timestamp cannot authorize free text through a direct
legacy tool call either. Still-valid windows continue to execute normally.

## Validation

The initial 12-case run had **eight failures and four passing controls**. All 12
cases pass after correction. Tests use controlled clocks and synchronization
events, rather than sleeps: they pause after initial validation at the execution
lock, advance the clock and then release the sender. They cover approved execution
and repeat invocation, source-only and fixture modes, expired and still-valid
windows, expiry during source checks, and direct legacy tool calls. Blocked cases
leave the mock outbox empty; positive controls intentionally record one mock send.

The focused window/source-approval/gateway suite passed **76 tests**. The complete
local Python 3.14 backend suite passed **1,557 tests**, with 149 integration skips,
four pre-existing expected failures, 662 passing subtests and three dependency/
configuration warnings. The expected failures concern existing recovery/fencing
protocol gaps. Ruff, formatting and strict mypy for WhatsApp tools passed.

Reproduce after installing development and document dependencies:

```text
python -m pytest tests/security/test_whatsapp_execution_window.py tests/security/test_whatsapp_timestamp_guards.py tests/security/test_source_bound_approvals.py tests/unit/test_tool_gateway.py -q
python -m pytest tests -q
python -m ruff check tools/whatsapp/tools.py tests/security/test_whatsapp_execution_window.py
python -m mypy tools/whatsapp
```

This is local verification, without live provider calls. The check does not recall
completed messages or cancel requests already in flight. Merging, deployment,
provider configuration and actual message delivery remain outside this record.
