# Email and WhatsApp supplied-source correction

Verified locally on 24 November 2026 against base application revision
`4f4b404d3762df3e12596cbeba41311dd18fa2ac` plus this PR's changes.

## Reproduced problems

Email ignored assigned sources and rendered a template containing an unsupported
licensed-advisor/contact promise. WhatsApp accepted the caller's arbitrary draft
without verifying it against its own sources and used a generic provider-template
name outside the service window. Before correction, 14 new regression cases failed
and two existing consent/opt-out boundary cases passed.

## Corrected behavior

In supplied-source mode, email requires a bounded `knowledge_query`, searches its
own customer-approved sources and uses a cited source title/body. WhatsApp searches
its own customer-approved sources using the incoming message, ignores unverified
draft text and quotes the resulting passages. Missing, unrelated, staff-only,
foreign, expired or removed sources cannot supply a draft. Outside-window WhatsApp
replies require staff review instead of an unverified provider-template fallback.

Only the read-only `documents.search` tool was added to these agents' existing
allowlists. Organization and agent identity come from trusted tool context. Send
requests retain the existing approval checks, marketing consent, WhatsApp opt-in,
opt-out and complaint handling. Developer fixture mode retains its previous
template behavior. Inbound email classification still works without knowledge.

## Validation

**145 focused tests passed**, including 20 messaging regressions and ownership
spoofing checks for all five source-consuming agents. Ruff, formatting and strict
mypy for email/WhatsApp passed. Tests used temporary SQLite stores and mock
providers; email and WhatsApp outboxes remained empty. One dependency deprecation
warning concerns FastAPI's test client using httpx.

Reproduce after installing development and document dependencies:

```text
python -m pytest tests/agents tests/security/test_agent_knowledge_isolation.py tests/security/test_assigned_source_api_isolation.py tests/evaluations tests/unit/test_assigned_agent_knowledge.py tests/unit/test_aws_knowledge_gateway.py -q
python -m ruff check agents/email agents/whatsapp tests/agents/test_messaging_assigned_sources.py tests/security/test_agent_knowledge_isolation.py
python -m mypy agents/email agents/whatsapp
```

This is local verification, not a deployment or provider integration. The separate
Follow-Up Agent still has its existing template workflow. Voice and other partial
agent capabilities remain as documented in the capability table.
