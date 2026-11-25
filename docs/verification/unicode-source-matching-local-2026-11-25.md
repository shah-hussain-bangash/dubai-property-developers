# Unicode supplied-source matching

Verified locally on 25 November 2026 against PR #87 revision
`aa4c1a7f06ce023d832f2eb1896a0fbee6ddd73e` plus this change.

## Observed issue

Supplied-source queries used the legacy hashing tokenizer's ASCII/Arabic-range
expression. Greek, Cyrillic and Chinese terms could disappear entirely; attached
Arabic punctuation could prevent a word match. Accented words could split into
unrelated fragments: `résumé` matched separate `r` and `sum` labels in a fictional
source. Arabic punctuation-only queries could also match punctuation instead of
a meaningful term. The initial 14-case run reported 11 failures and three passing
controls.

## Correction

A separate Unicode lexical tokenizer now handles supplied-source question and
passage matching. It case-folds/canonically normalizes matching keys, recognizes
letter/number runs with attached combining marks, and treats punctuation/symbols
as separators. Existing English stopword filtering remains. Original stored
pages and cited excerpts are not normalized or rewritten.

Only `AssignedSources` uses the new tokenizer. The legacy `tokenize` function,
hashing embedder, model name and vector representation remain unchanged, avoiding
an implicit stored-vector format change. Source ownership, customer-approval,
review-date, match-threshold and ranking rules are unchanged.

## Verification

All **17 new cases passed**: accent/Arabic/Chinese/Greek/Cyrillic/case-fold matching,
punctuation rejection, unrelated-fragment rejection, staff/customer/foreign scope
checks, existing stopwords, legacy hashing compatibility, a saved-source API
answer, canonical accent equivalence, Arabic combining marks and stray marks.
Three tokenizer controls were added after the initial source-level regression
run. The focused source/API/messaging/document suite passed **73 tests**.

The full local Python 3.14 suite reported **1,864 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three existing dependency or
configuration warnings. Integration skips require explicitly enabled services;
expected failures concern existing recovery/fencing gaps. Ruff, formatting and
mypy for the two knowledge source files passed.

```text
python -m pytest tests/unit/test_unicode_source_matching.py tests/unit/test_assigned_agent_knowledge.py tests/security/test_assigned_source_api_isolation.py tests/agents/test_messaging_assigned_sources.py tests/agents/test_document_assigned_summaries.py -q
python -m pytest -q
python -m mypy knowledge/embeddings/base.py knowledge/assigned_sources.py
```

## Limits

Matching remains lexical, not semantic or translated. CJK letter runs are not
segmented into linguistic words; canonical matching does not remove all accents
or infer morphology. The legacy vector/demo search path intentionally retains
its existing tokenizer. No new model, persisted index migration, source rewrite,
live CRM write, customer message, merge or deployment occurred.
