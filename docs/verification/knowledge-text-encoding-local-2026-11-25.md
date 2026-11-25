# Knowledge text encoding fidelity

Verified locally on 25 November 2026 against PR #87 revision
`6f4096e5dc281fbc977c758eb89a29dbd8b4ff04` plus this change.

## Observed issue

Text, Markdown and HTML extraction decoded all input as UTF-8 with replacement
enabled. Malformed or unsupported bytes silently became replacement characters
and could be saved and quoted as knowledge. BOM-marked UTF-16/UTF-32 files were
also misread, and a UTF-8 signature could remain in the stored text. The initial
18-case regression run reported 16 failures and two passing UTF-8 controls.

## Correction

Text extraction now decodes strictly. It recognizes UTF-32 signatures before
UTF-16 signatures, then uses UTF-8 with optional signature handling otherwise.
Supported signatures are removed as encoding metadata; the decoded text retains
its Unicode characters. Unreadable byte sequences raise a bounded validation
error with no input content or bytes in the message. HTML still passes decoded
text through the existing hidden-script/style extraction. PDF processing and
input size/page/character limits are unchanged.

## Verification

All **18 new cases passed**: UTF-8 with/without signature, UTF-16 little/big endian,
UTF-32 little/big endian, Unicode HTML/Markdown, hidden-script exclusion,
malformed/truncated byte sequences, unsupported legacy bytes, exact Unicode
upload-to-answer excerpts, separate-agent ownership and rejection without saving
an unreadable file. The combined encoding/import/authenticated source-scope
suite passed **71 tests**.

The full local Python 3.14 suite reported **1,829 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three existing dependency or
configuration warnings. Integration skips require explicitly enabled services;
expected failures concern existing recovery/fencing gaps. Ruff, formatting and
mypy for the importer passed.

```text
python -m pytest tests/unit/test_knowledge_text_encoding.py tests/unit/test_assigned_agent_knowledge.py tests/unit/test_international_knowledge_links.py tests/unit/test_knowledge_import_fetch_budget.py tests/security/test_assigned_source_api_isolation.py -q
python -m pytest -q
python -m mypy knowledge/ingestion/assigned_inputs.py
```

## Limits

Legacy encodings and arbitrary HTTP charset declarations are not newly supported;
unreadable inputs now fail instead of being silently changed. Convert those
sources to UTF-8 or paste text. Unmarked UTF-16/32 is not inferred. Previously
saved sources are untouched; re-import is needed to replace previously damaged
text. This does not add OCR, translation or live website verification. No live
CRM writes, customer messages, merge or deployment occurred.
