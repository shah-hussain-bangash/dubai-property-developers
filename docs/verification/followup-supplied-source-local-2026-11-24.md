# Follow-up supplied-source correction

Verified locally on 24 November 2026 against base application revision
`4f4b404d3762df3e12596cbeba41311dd18fa2ac` plus the source-only changes in this PR.

## Observed problem

With supplied-source mode enabled, the separate Follow-Up Agent still rendered a
fixed email template and requested a generic WhatsApp provider template. Missing,
staff-only, foreign or unrelated sources did not prevent action preparation.
The initial regression run reproduced **18 failures**, with one existing task-guard
case passing. No provider or hosted customer records were accessed.

## Corrected behavior

Each follow-up task requires a bounded `knowledge_query`. The agent searches only
its own organization's customer-approved Follow-Up Agent sources. The action body
quotes cited passages and email send requests use the source title as their subject.
No fixed template is attached to a supplied-source action (`template` is null).
Missing queries or relevant sources produce a task escalation and no action.
Removing a source prevents it from supplying subsequent follow-ups.

WhatsApp follow-ups use the cited text inside the current service window. Outside
that window, or without a last inbound message, staff review is required instead
of an unverified provider-template fallback. Existing consent, customer reply,
status, due-date and attempt checks still run. Only grounded eligible actions can
request approval. Unsupported tasks do not block supported tasks in the same batch.

Only read-only `documents.search` was added to the existing tool allowlist; the
gateway derives agent and organization identity from trusted execution context.
Existing fixture-mode templates are retained. Database task sourcing, scheduled
worker triggers and live provider setup remain incomplete.

## Validation

**169 focused tests passed**, including 21 follow-up cases, worker handlers and
ownership-spoofing checks for all six source-consuming agents. Ruff, formatting and
strict mypy for the Follow-Up Agent passed. All email and WhatsApp mock outboxes
remained empty; dispatch tests created approval requests without executing them.
One dependency deprecation warning concerns FastAPI's test client using httpx.

Reproduce after installing development and document dependencies:

```text
python -m pytest tests/agents tests/security/test_agent_knowledge_isolation.py tests/security/test_assigned_source_api_isolation.py tests/evaluations tests/unit/test_assigned_agent_knowledge.py tests/unit/test_aws_knowledge_gateway.py tests/unit/test_worker_handlers.py -q
python -m ruff check agents/followup tests/agents/test_followup_assigned_sources.py tests/security/test_agent_knowledge_isolation.py
python -m mypy agents/followup
```

This record is local evidence. It does not merge, deploy, enable scheduling or send
messages from the hosted portfolio website.
