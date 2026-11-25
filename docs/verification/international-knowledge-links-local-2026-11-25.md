# International website knowledge links

Verified locally on 25 November 2026 against PR #87 revision
`0c08be8d80bfdb39bdc6c388c687e4b34d4d3be8` plus this change.

## Observed blocker

The importer converted international hostnames to IDNA but passed non-ASCII
paths and queries directly into the HTTP request line. Links containing Arabic,
Chinese or accented page names therefore failed request encoding and returned
the generic unreachable-page validation error. Redirects to those paths failed
the same way. The initial regression run reported eight failures and eight
passing compatibility/security controls.

## Correction

The checked request path and query now use UTF-8 percent encoding through Python's
standard [URL quoting function](https://docs.python.org/3/library/urllib.parse.html#urllib.parse.quote).
Existing percent escapes and query separators are retained; encoded slashes,
ampersands and equals signs are not decoded or double-encoded. Host verification,
public-address DNS checks, pinned connection addresses and redirect revalidation
remain in place. Only the transport request target changes; saved source links
retain the supplied/final redirect URL for provenance.

## Verification

All **16 new cases passed**, covering Arabic, Chinese, accents, IDNA hostnames,
already-escaped and mixed links, query separators, relative/absolute redirects,
private-address rejection, existing scheme/user-info/port/control/fragment
restrictions and an HTTP source import followed by a cited staff answer. The
API case confirms the saved URI stays intact and another agent has no answer.
The combined import and authenticated source-isolation suite passed **41 tests**.

The full local Python 3.14 suite reported **1,799 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three existing dependency or
configuration warnings. Integration skips require explicitly enabled services;
expected failures concern existing recovery/fencing gaps. Ruff, formatting and
mypy for the importer passed. All 16 new controls were also rerun successfully
after simplifying the user-info fixture.

```text
python -m pytest tests/unit/test_international_knowledge_links.py tests/unit/test_assigned_agent_knowledge.py tests/security/test_assigned_source_api_isolation.py -q
python -m pytest -q
python -m mypy knowledge/ingestion/assigned_inputs.py
```

## Limits

DNS and HTTP transport are simulated; the fake transport enforces the same ASCII
request-line constraint without opening a socket. No external website request
was used for regression evidence. This does not add crawling, authenticated
imports, new content encodings or model-generated answers. No live CRM writes,
customer messages, merge or deployment occurred.
