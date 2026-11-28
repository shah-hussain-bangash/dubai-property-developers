# Document summary supplied-source correction

Verified locally on 24 November 2026 against base application revision
`4f4b404d3762df3e12596cbeba41311dd18fa2ac` plus this PR's changes.

## Observed problem

The Document Agent's answer path used assigned knowledge, but its summary path
returned arbitrary caller-provided text without retrieving sources or citations,
even with supplied-source mode enabled. All 11 new summary regressions failed
before correction, including missing/foreign-source refusal and valid own-source
summaries. The fixtures used fictional claims, not customer records.

## Corrected behavior

In supplied-source mode, `action: "summarize"` requires a query and shares the answer
path's scoped retrieval. The summary extracts sentences only from cited passages
belonging to the Document Agent and authenticated organization. Unassigned caller
text is ignored. Missing queries or relevant sources request human review without
a summary. Removed and expired sources cannot supply subsequent summaries.

Customer summaries require customer-approved material. Explicit staff summaries
can use the agent's own staff-only material through the existing authenticated
read permission. Source citations, including PDF passage references, are retained.
The summary covers retrieved matching passages, not an entire original document.
Developer fixture mode retains direct text summaries. No tools or permissions were
added, and no model generation is used.

## Validation

**180 focused tests passed**, including 11 summary regressions, all-agent source
isolation, six consumers' trusted-context boundaries and worker handlers. Ruff,
formatting and strict mypy for the Document Agent passed. All message outboxes in
the summary fixtures remained empty. One dependency deprecation warning concerns
FastAPI's test client using httpx.

Reproduce after installing development and document dependencies:

```text
python -m pytest tests/agents tests/security/test_agent_knowledge_isolation.py tests/security/test_assigned_source_api_isolation.py tests/evaluations tests/unit/test_assigned_agent_knowledge.py tests/unit/test_aws_knowledge_gateway.py tests/unit/test_worker_handlers.py -q
python -m ruff check agents/documents tests/agents/test_document_assigned_summaries.py
python -m ruff format --check agents/documents tests/agents/test_document_assigned_summaries.py
python -m mypy agents/documents
```

This is local evidence. It does not merge or deploy the PR, configure providers,
send messages or make partial agents fully operational.
