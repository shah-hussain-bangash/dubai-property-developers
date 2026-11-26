# Separate agent knowledge evaluations

Verified locally on 26 November 2026 against parent
`ff71f97eb1ffd6eaabd7cc7c51f4cb213f782b76` plus this increment in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the evaluated implementation.
This is local evidence, not hosted staging acceptance or a deployment.

## Behavior

The Knowledge page now supports a separate question set for the selected agent.
Staff can add up to 20 questions, choose expected passage or no-answer outcomes,
save an agent-bound JSON file, reload it and download actual results with citations.
The page supplies the file format; users do not need to edit JSON.
Questions are held in the page and saved on the user's device, not persisted in
the source database. Switching agents clears the current set; save it first.
Changing questions or refreshing changed source data clears displayed results.

An answer check requires the expected text to occur inside an actual returned
excerpt, with matching capital letters. Titles and citation labels cannot satisfy
that check. A no-answer check requires the existing explicit abstention. This is
a deterministic retrieval check, not an assessment of general model reasoning,
fine-tuning, customer delivery or completeness of all agent capabilities.

The authenticated `POST /api/v1/knowledge/agents/{agent}/evaluate` endpoint uses
the principal's organization and registered agent. It requires knowledge-read
permission, validates bounded unique cases and route/set ownership, and retrieves
using only each question. Expected passages never enter retrieval or source
storage. The response is private/no-store and sends no customer reply. Staff-only
sources remain eligible here, as in the existing staff question preview.
Keep downloaded files private when evaluating private material.

## Reproduce the fictional page journey

1. Start the repository's local API and dashboard with mock providers, persistent
   disposable source storage and the dashboard pointing to that API. Sign in to
   the local admin workspace and open Knowledge. Use existing local setup guidance;
   do not point this rehearsal at live CRM or messaging providers.
2. Select Document Agent. Add pasted text titled `Fictional evaluation guide`:
   `Fictional project contains eight gardens.` Leave customer approval unchecked.
3. In Saved checks, enter `project gardens`, choose Should find a passage, and
   enter expected passage `eight gardens`.
4. Add `quasar telescope` and choose Should say not found. Run saved checks:
   **2 of 2 passed**, with the original source quote and an explicit abstention.
5. Save question set. Change the first question, then load the saved file. The
   original two questions return. Run again: **2 of 2 passed**. Download results.
6. Select Marketing Agent and try loading the Document Agent file. The page
   rejects it; Marketing's source list and question fields remain empty.
7. Sign out and stop the disposable servers. Temporary login material was removed.

[Downloaded fictional report](agent-knowledge-evaluation-local-2026-11-26.json)
retains the question set, agent identity, outcomes and source content ID.
[Page capture](assets/agent-knowledge-evaluation-2026-11-26.jpg) records the second
successful run. Only fictional material is included. Browser checks used the local
development identity; authenticated tenant/role boundaries were tested separately.

## Checks

- **29 new API regression cases pass**: all 13 agents, organization separation,
  viewer read access, missing-source/foreign-source abstention, expected-text
  non-ingestion, source changes, title-only mismatch, authentication, invalid
  ownership, duplicate IDs, field/count/body limits and unknown-agent rejection.
- **19 new dashboard cases pass**: actual quotes/PDF references, agent switching,
  editing, adding/removing questions, loading/saving, failed file validation,
  in-flight locking and rejection of forged counts, outcomes or citations.
- Full local backend: **2,293 passed**, 156 skipped, four existing expected
  failures, 662 passing subtests; three warnings. Database integration prerequisites
  and Unix-only mode checks account for local skips. Recovery/fencing expected
  failures remain documented limitations.
- Full dashboard: **974 tests in 96 files passed**. Type checking and production
  compilation pass. Lint has zero errors and 27 existing warnings. The existing
  Windows standalone packaging symlink warning remains; use a verified release
  artifact rather than this local standalone output.
- Ruff, Python formatting and focused mypy pass for changed Python files.

The initial GitHub frontend run exposed a readiness race in the existing website
link test: actions could become enabled between agent selection and the source
loading effect. The panel now also requires the source list's loaded agent to
match the selected agent. A delayed-list regression covers this guard. The
existing source-link/switching tests and the new evaluation tests pass together
in a 43-case focused run. The final frontend totals above include this correction.
The browser capture predates this readiness-only correction; the evaluation API,
question-file contract, actual outcomes and displayed form are unchanged.

From the source root with the project environment:

```text
python -m pytest tests/security/test_agent_knowledge_evaluation.py -q -p no:cacheprovider --basetemp=../fresh-evaluation-review
python -m pytest -q -p no:cacheprovider --basetemp=../fresh-evaluation-full
python -m ruff check knowledge/evaluation/supplied_sources.py apps/api/app/api/v1/routes/agent_knowledge.py tests/security/test_agent_knowledge_evaluation.py
python -m ruff format --check knowledge/evaluation/supplied_sources.py apps/api/app/api/v1/routes/agent_knowledge.py tests/security/test_agent_knowledge_evaluation.py
python -m mypy knowledge/evaluation/supplied_sources.py apps/api/app/api/v1/routes/agent_knowledge.py
```

From `apps/dashboard`, run `npm test -- --reporter=dot`, `npm run typecheck`,
`npm run lint` and `npm run build`. The focused new file is
`src/__tests__/AgentKnowledgeEvaluation.test.tsx`.

No source schema migration, merge, deployment or live provider write is included.
Hosted verification still depends on restored AWS access. Evaluation sets are
local files; server-side shared datasets and historical evaluation tracking remain
future work.
