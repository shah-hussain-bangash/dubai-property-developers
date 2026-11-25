# Website import fetch budget

Verified locally on 25 November 2026 against PR #87 revision
`97e9c8db267ba8c86ab4ea4fd88f879d4e2902cd` plus this change.

## Observed blocker

The importer started its elapsed-time budget only after receiving response
headers. Redirects therefore consumed no shared fetch budget. Body reads checked
elapsed time only for non-empty chunks, allowing a late end-of-stream response
to bypass the check. A simulated HTTP import accepted and saved a source whose
final read arrived after the intended limit. The initial 12-case run reported
ten failures and two passing controls.

## Correction

One 20-second monotonic fetch budget now covers the entire redirect chain.
Checks run before/after DNS resolution, connection setup, sending the request,
receiving headers and every body read, including empty EOF reads. An observed
expiry raises the existing validation error instead of accepting the response
or starting a further hop. Created connections close through the existing
`finally` block. URL checks, IP pinning, redirect-count limits and source-size
limits remain unchanged.

## Verification

All **12 new cases passed**: late DNS/setup/request/headers/body/EOF phases,
redirects sharing a budget, no additional hop after observed expiry, the exact
deadline boundary, normal below-budget redirects, cleanup and an API validation
error with no saved source. The fake clock replaces only this module's clock
reference, leaving the event loop and test framework clocks intact. No real
waiting or network requests are needed. The combined budget/import/source-scope
suite passed **53 tests**.

The full local Python 3.14 suite reported **1,811 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three existing dependency or
configuration warnings. Integration skips require explicitly enabled services;
expected failures concern existing recovery/fencing gaps. Ruff, formatting and
mypy for the importer passed.

```text
python -m pytest tests/unit/test_knowledge_import_fetch_budget.py tests/unit/test_international_knowledge_links.py tests/unit/test_assigned_agent_knowledge.py tests/security/test_assigned_source_api_isolation.py -q
python -m pytest -q
python -m mypy knowledge/ingestion/assigned_inputs.py
```

## Limits

This is an elapsed-time acceptance budget checked around blocking operations,
not forced cancellation at exactly 20 seconds. A blocked DNS/socket operation
may return later before expiry is detected; existing socket timeouts still apply.
PDF/text extraction follows successful fetching and is outside this network
budget. No new process isolation, DNS cancellation, live website verification,
customer messages, live CRM writes, merge or deployment occurred.
