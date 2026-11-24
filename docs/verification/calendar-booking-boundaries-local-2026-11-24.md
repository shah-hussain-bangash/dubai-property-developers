# Calendar booking boundaries

Verified locally on 24 November 2026 against PR #87 revision
`7509cbcdaa2cf7619989b205121f1d4d4fb2206f` plus this change.

## Observed blockers

The calendar tool forwarded a raw caller key, or a title/start-time fallback,
to its shared provider client. Different approved bookings could therefore
collapse into one mock event when attendees, end time or description changed.
The runtime calendar also lacked a configured-account organization check, so
another organization could request a booking or replay an old cached result.
Time validation raised raw type errors for non-string/mixed timestamps and
accepted timezone-ambiguous values; standalone execution skipped validation.
The initial 28-case regression run reported 22 failures and six passing controls.

## Correction

The runtime calendar tool is bound to `DEFAULT_TENANT_ID`. It uses the existing
context-authorization hook before approval creation, cached replay and approved
execution, and rechecks ownership at its direct contextual entry point. Missing
bindings, mismatched principal/context organizations, foreign approvals and
unscoped calls to a bound tool fail closed.

Contextual provider keys hash the trusted organization, agent and entire approved
payload using the existing shared helper. Distinct approved events and agent
identities retain distinct keys. Exact retries keep their key after gateway
cache loss. Unbound standalone adapters retain explicit legacy keys.

All send paths validate start/end before the provider call. Invalid values become
domain validation errors, both timestamps require an explicit UTC offset, and
end must follow start. Valid offsets are preserved rather than replaced with
the host's local timezone. Actual agent allowlists and capabilities are unchanged.

## Verification

All **31 new cases passed**, including different approved attendees/end times/
descriptions, same-event retry, trusted agent separation, foreign requests/cache
entries/old approvals, missing and spoofed identity, non-default account ownership,
UTC-offset preservation, invalid or ambiguous times, and standalone compatibility.
The combined calendar/CRM/agent/gateway suite passed **86 tests**.

The full local Python 3.14 suite reported **1,727 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three existing dependency or
configuration warnings. Integration skips require explicitly enabled services;
expected failures concern existing recovery/fencing gaps. Ruff, formatting and
mypy for three calendar/runtime source files passed.

```text
python -m pytest tests/security/test_calendar_booking_boundaries.py tests/security/test_crm_account_binding.py tests/security/test_agent_action_isolation.py tests/unit/test_tool_gateway.py -q
python -m pytest -q
python -m mypy tools/calendar workflows/runtime.py
```

## Limits

The calendar remains a mock adapter; Google OAuth, live calendar access, provider
deduplication and distributed exactly-once booking are not verified or enabled.
Additional organizations need explicit calendar account routing. No customer
invitation, real calendar write, merge or deployment occurred.
