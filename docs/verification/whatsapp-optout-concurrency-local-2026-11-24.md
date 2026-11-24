# WhatsApp opt-out concurrency and queued replies

Verified locally on 24 November 2026 against base application revision
`4f4b404d3762df3e12596cbeba41311dd18fa2ac` plus this PR's changes.

## Reproduced problems

The WhatsApp Agent read a state snapshot and later replaced the entire state. A
normal message paused after that read could overwrite an opt-out recorded while
it waited. A reply queued before withdrawal could also execute after the customer
opted out because send approval only retained the original consent flag. The
initial six-case run had four failures and two passing organization-isolation controls.

## Correction

Conversation memory now exposes an atomic top-level `update_state` patch. Normal
WhatsApp messages patch their current inbound/contact/consent fields without
clearing `opted_out`; explicit unsubscribe events latch that flag. The process-local
store updates without an intervening await, while SQL merges under a row lock and
preserves other fields/agent partitions. Returned and input snapshots remain detached.

WhatsApp Agent approvals retain the conversation reference. The configured send
tool uses trusted organization/agent scope to recheck current opt-out, consent and
recipient before the provider call. Missing, unknown or foreign references cannot
provide consent. Direct execution without trusted context is rejected when the
runtime memory binding is configured. Valid source and timing checks still apply.
Cached completed results replay without delivering a second message; the reference
is not added as a new provider message field.

## Validation

The expanded opt-out suite passed **20 cases** in fixture and source-only modes.
It covers the forced stale-write interleaving, queued replies after opt-out or
consent withdrawal, recipient changes, forged references, organization isolation,
detached atomic-patch results and completed-send replay. The combined local
agent/source/approval/memory/window suite passed **216 tests**. No timing sleeps are
used to reproduce the stale write: synchronization events control the interleaving.

The full local Python 3.14 suite reported **1,596 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three dependency/configuration
warnings. The expected failures concern existing recovery/fencing protocol gaps.
Ruff, formatting and strict mypy for 11 source files passed.

Two additional PostgreSQL cases run in CI: preserving opt-out/agent partitions
under patches and applying concurrent patches through separate connections. The
concurrent case creates exclusively owned fictional UUID records, then deletes
only those records in cleanup; the other database fixtures roll back their changes.

Reproduce after installing development and document dependencies:

```text
python -m pytest tests/security/test_whatsapp_optout_races.py -q
python -m pytest tests -q
python -m mypy core/memory database/repositories/conversation_memory.py agents/whatsapp tools/whatsapp workflows/runtime.py
```

With the disposable integration database configured and `RUN_INTEGRATION_TESTS=1`:

```text
python -m pytest tests/integration/test_scoped_conversation_memory.py -q
```

This is per-conversation WhatsApp Agent protection, not a durable contact-wide
consent registry or automatic CRM/Follow-Up consent synchronization. Explicit
opt-out is not automatically reset by a new message. Default memory remains
process-local. A request already in flight cannot be recalled, and delivered
messages are not undone. Only mock sends execute in these tests; no live provider,
CRM, merge or deployment was used.
