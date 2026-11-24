# Source-bound approval execution

Verified locally on 24 November 2026 against base application revision
`4f4b404d3762df3e12596cbeba41311dd18fa2ac` plus this PR's changes.

## Observed gap

Draft preparation checked assigned knowledge, but approval execution only rechecked
ordinary send validation and permissions. Queued email, WhatsApp and follow-up
messages could execute against the mock provider after their source was removed,
expired, renamed or no longer customer-approved. Arbitrary source metadata/body
changes also passed. The initial regressions produced **26 failures and four passes**.

## Correction

Source-only agents attach citation snapshots to private send-approval payloads.
The gateway retains the stored original agent identity when executing an approval.
Before a new provider call, contextual email/WhatsApp tools verify all references
against that agent and organization in the current assigned-source store. They
check current customer approval/review date, title, source and chunk identifiers,
version, exact passage text and the complete assembled message. Email subjects
must match the first source title. Missing/forged citations, unscoped callers,
altered content and unverified provider templates cannot authorize a send.

The check is repeated at execution rather than trusting draft-time evidence.
It applies to Email, WhatsApp and both Follow-Up channels. Source metadata is not
forwarded to providers. Developer fixture mode retains its previous behavior.
Successful cached executions replay without another provider call, including after
source removal; a completed message cannot be recalled. The guard checks current
sources immediately before calling a provider. It does not hold database locks
across network delivery or guarantee cancellation of requests already in flight.

A blocked action can retain the human-approved decision in the approval store,
but execution raises a policy error and no provider call occurs. The operator must
prepare and review a fresh draft; this change adds no new approval status.

## Validation

All **37 approval-specific cases passed**, covering withdrawal, expiry, removal,
retitling, all four sender paths, forged/missing references, subject/body changes,
multiple sources/PDF references, unscoped execution and successful one-time mock
execution with cached replay. Positive tests deliberately execute mock sends;
blocked cases leave both mock outboxes empty. No live provider was called.

The full local Python 3.14 backend suite reported **1,545 passed, 149 skipped and
four expected failures**, plus 662 passing subtests. Skips primarily require local
integration services. The four existing expected failures concern recovery/fencing
protocol gaps and remain unresolved. Three dependency/configuration deprecation
warnings were reported. Ruff, formatting and strict mypy for 20 changed/imported
source files passed. GitHub runs the database integrations separately.

Reproduce after installing development and document dependencies:

```text
python -m pytest tests/security/test_source_bound_approvals.py -q
python -m pytest tests -q
python -m ruff check knowledge/assigned_sources.py tools/base.py tools/email/tools.py tools/whatsapp/tools.py workflows/runtime.py agents/email/agent.py agents/whatsapp/agent.py agents/followup/agent.py tests/security/test_source_bound_approvals.py
python -m mypy knowledge/assigned_sources.py tools/email tools/whatsapp tools/base.py workflows/runtime.py agents/email agents/whatsapp agents/followup
```

This evidence is local. It does not merge/deploy the PR, configure providers,
activate scheduling or send live CRM/email/WhatsApp writes.
