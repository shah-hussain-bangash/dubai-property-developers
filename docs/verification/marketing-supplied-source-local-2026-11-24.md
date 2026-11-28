# Marketing supplied-source draft correction

Verified locally on 24 November 2026. Base application revision:
`4f4b404d3762df3e12596cbeba41311dd18fa2ac`, with the changes in this PR.

## Observed problem

With `AGENT_KNOWLEDGE_PATH` enabled and no assigned sources, the Marketing Agent
still returned a successful campaign draft claiming “New options” and “We have
curated options”. Its template did not consult supplied knowledge. A regression
run reproduced five failures: missing, staff-only, foreign-agent and foreign-tenant
sources did not stop drafting, and an approved own source was ignored.

## Resulting behavior

In supplied-source mode, the Marketing Agent uses the campaign goal to search only
its own organization's customer-approved marketing sources. The headline uses the
source title; the body quotes cited source passages. Missing or unrelated sources
produce no draft and an escalated result requesting human review. Removed sources
cannot supply the next draft. Lead segmentation still requires marketing consent.

The only added tool is the existing read-only `documents.search`, using trusted
agent/tenant context and the customer audience filter. The agent has no send tool;
drafts remain labelled `draft_requires_approval`. Existing developer fixture mode
retains its template behavior. No model or external provider is called.

## Reproduce

Install development and document dependencies and run from the repository root:

```text
python -m pytest tests/agents tests/security/test_agent_knowledge_isolation.py tests/security/test_assigned_source_api_isolation.py tests/evaluations tests/unit/test_assigned_agent_knowledge.py tests/unit/test_aws_knowledge_gateway.py -q
python -m ruff check agents/marketing tests/agents/test_marketing_assigned_sources.py tests/security/test_agent_knowledge_isolation.py tests/agents/test_registry_and_base.py
python -m mypy agents/marketing
```

All data is fictional and stored locally. This verification does not update the
hosted website or enable campaign delivery, voice services or other partial agents.

After the correction, **123 focused tests passed**, including seven marketing
source/consent cases, all-agent API isolation and the existing evaluations. Ruff
checks, formatting and strict mypy for the Marketing Agent also passed.
