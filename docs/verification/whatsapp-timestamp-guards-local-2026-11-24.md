# WhatsApp timestamp guard verification

Verified locally on 24 November 2026 against base application revision
`4f4b404d3762df3e12596cbeba41311dd18fa2ac` plus the changes in this PR.

## Observed problems

The shared service-window helper checked only whether age was less than or equal
to 24 hours. A future inbound timestamp therefore opened a free-text window and
could create a send approval request through WhatsApp or Follow-Up, even in
supplied-source mode. A naive comparison clock could raise a timezone error.
Malformed send timestamps either raised raw parsing errors or were treated as
missing values, depending on their type. The initial 18-case regression run had
12 failures and six passes.

## Correction

The repository's existing inclusive 24-hour window now has a lower bound too:
`0 <= now - last_inbound_at <= 24 hours`. Future and missing inbound times cannot
authorize free text. The helper interprets legacy naive inbound/comparison clocks
as UTC; equivalent aware timezone values retain their normal behavior. Malformed
timestamp strings and unsupported types raise a domain validation error before
approval, without returning their raw values in the message.

The shared helper protects WhatsApp Agent replies, Follow-Up Agent free-text
planning and the send tool's own approval gate. This does not add a provider,
enable a template fallback, change the 24-hour upper bound or remove approval.

## Validation

**219 focused tests passed**, including 18 timestamp cases, the existing source
boundaries, security controls, tool gateway checks and worker handlers. Ruff,
formatting and strict mypy for WhatsApp tools passed. All timestamp fixtures are
fictional; no message was sent and future timestamps produced no approval request.
One dependency deprecation warning concerns FastAPI's test client using httpx.

Reproduce after installing development and document dependencies:

```text
python -m pytest tests/agents tests/security/test_agent_knowledge_isolation.py tests/security/test_assigned_source_api_isolation.py tests/security/test_whatsapp_timestamp_guards.py tests/security/test_security_controls.py tests/evaluations tests/unit/test_assigned_agent_knowledge.py tests/unit/test_aws_knowledge_gateway.py tests/unit/test_worker_handlers.py tests/unit/test_tool_gateway.py -q
python -m ruff check tools/whatsapp tests/security/test_whatsapp_timestamp_guards.py
python -m ruff format --check tools/whatsapp tests/security/test_whatsapp_timestamp_guards.py
python -m mypy tools/whatsapp
```

This is local verification. The PR remains separate from merging, deployment,
provider configuration and actual message delivery.
