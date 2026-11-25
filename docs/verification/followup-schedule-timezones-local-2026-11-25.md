# Follow-Up scheduling timezone consistency

Verified locally on 25 November 2026 against PR #87 revision
`bd8ac9a644446766539e9de323356182c021c462` plus this change.

## Observed blocker

Follow-Up compared `due_at` directly with its planning clock and subtracted the
original value for overdue checks. Mixing offset-aware and offset-less timestamps
raised a Python type error and failed the entire batch, including otherwise valid
tasks. Omitting the planning-clock override also failed for a legacy naive task
because the default clock is UTC-aware. The initial 24-case run reported 18
failures and six passing compatibility controls.

## Correction

Planning-clock, due-time comparison and overdue arithmetic now use UTC consistently.
Legacy naive backend timestamps mean UTC, following the existing messaging policy
convention; explicit offsets are converted to the same instant in UTC. Callers
should include offsets in new schedule data. Input task models are not mutated.
Due/overdue thresholds, status/consent/attempt checks, source scopes, send payloads,
approval requirements and replay rules are unchanged.

## Verification

All **24 new cases passed** across fixture/source-only modes: naive due/current
times, both naive, explicit offsets, due exactly now, not-yet-due, exactly 48 hours
overdue and just beyond it, mixed batches, the default clock, unchanged supplied
models, and workflow-to-approval delivery/replay. The mock email outbox stays empty
until approval, records one delivery, and remains one after replay. Source-only
copy still equals the approved own-source excerpt. The focused scheduling/source/
window/workflow/delivery-key suite passed **83 tests**.

The full local Python 3.14 suite reported **1,916 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three existing dependency or
configuration warnings. Integration skips require explicitly enabled services;
expected failures concern existing recovery/fencing gaps. Ruff, formatting and
mypy for three Follow-Up source files passed.

```text
python -m pytest tests/security/test_followup_schedule_timezones.py tests/agents/test_followup_assigned_sources.py tests/security/test_whatsapp_timestamp_guards.py tests/workflows/test_workflows.py tests/security/test_delivery_key_isolation.py -q
python -m pytest -q
python -m mypy agents/followup
```

## Limits

No local timezone is inferred for offset-less values; UTC is the declared legacy
convention. This does not add a scheduler trigger, persistent task loader, contact-wide
consent source or live delivery provider. Malformed timestamp input retains existing
schema validation. No live CRM writes, customer messages, merge or deployment occurred.
