# Agent source boundary verification

Verified locally on 24 November 2026 against main application revision
`4f4b404d3762df3e12596cbeba41311dd18fa2ac`, with the regression tests in this PR.
This verification used temporary SQLite files, fictional identities and mock providers.
It did not access hosted knowledge, customer records, live CRM or outbound messaging.

## Results

The focused suite passed **115 tests**, including the 39 held-out per-agent evaluation
cases and three new authenticated HTTP boundary tests. Ruff passed for the new tests.
One dependency deprecation warning concerned FastAPI's test client using httpx.

The new HTTP checks cover:

- All 13 registered agents in two fictional organizations. After restarting the app,
  each source list and cited answer contains only that owner’s supplied material.
- Missing information returns no answer, without generated or fixture fallback.
- All 338 foreign-source deletion attempts return 404; every original source remains.
- Identical content produces the same content hash across 26 owners. Deleting one
  owner’s copy leaves the other 25 copies available.
- Anonymous reads are denied for every agent. Viewers cannot import or remove sources,
  including with spoofed admin or organization headers. Answer payloads cannot override
  the authenticated organization.

No application defect was observed, so application behavior was not changed. The
regressions extend the existing store/retriever checks through the authenticated API.

## Reproduce

Install the repository's development and document dependencies, then run from its root:

```text
python -m pytest tests/agents tests/security/test_agent_knowledge_isolation.py tests/security/test_assigned_source_api_isolation.py tests/evaluations tests/unit/test_assigned_agent_knowledge.py tests/unit/test_aws_knowledge_gateway.py -q
python -m ruff check tests/security/test_assigned_source_api_isolation.py
python -m ruff format --check tests/security/test_assigned_source_api_isolation.py
```

These results establish source isolation and the tested behaviors. They do not make
partial agents or the voice interface fully operational, configure external providers,
or separately fine-tune models. See the [capability table](../agents/README.md).
