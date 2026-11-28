# Independent property catalog snapshots

Verified locally on 25 November 2026 against PR #87 revision
`037d6e345dc7e1b03021ae8ecf1fcf29933832de` plus this change.

## Observed issue

The read-only in-memory catalog retained the caller's listing objects and
returned those same mutable models from `get` and `all_listings`. Default catalog
instances also shared the global fictional seed models. Changing prices,
availability, demo/source labels or nested payment-plan details through one
returned record changed other catalog instances and could alter future defaults.
This is an internal model-aliasing issue; existing serialized tool responses
were already detached and did not provide a public inventory-write endpoint.

## Correction

The catalog deep-copies each listing during construction and returns independent
deep snapshots from both read methods. Generator inputs remain supported, unknown
IDs still return `None`, and empty catalogs remain empty. Search/matching rules,
fixture values, property-agent capabilities and runtime source configuration are
unchanged. The protocol now states that returned models are read-only snapshots
and edits do not update inventory.

## Verification

All **ten new cases passed**: list/generator inputs, both read methods, nested
payment plans, two catalogs sharing an input, global default-seed isolation,
serialized search/match response edits, empty/unknown reads, and the supplied-source
workspace's disabled demo inventory. With a valid payment-plan fixture, the
pre-fix run had six failing snapshot cases and three passing compatibility controls;
the supplied-source control was added afterward. Tests restore the global seed
even when demonstrating the old failure, preventing interference with other cases.

The focused catalog/matching/agent/workflow suite passed **44 tests**. The full
local Python 3.14 suite reported **1,783 passed, 155 skipped, four existing expected
failures and 662 passing subtests**, with three existing dependency/configuration
warnings. Integration skips require explicitly enabled services; expected failures
concern existing recovery/fencing gaps. Ruff, formatting and mypy for four property
source files passed.

```text
python -m pytest tests/unit/test_property_catalog_snapshots.py tests/unit/test_scoring_and_matching.py tests/agents/test_agents.py tests/workflows/test_workflows.py -q
python -m pytest -q
python -m mypy tools/property
```

## Limits

This does not introduce live inventory, inventory editing, organization-specific
catalog feeds or automatic extraction of structured listings from uploaded PDFs.
Supplied-source workspaces retain their empty typed catalog and do not fall back
to demo recommendations. Quoted uploaded knowledge remains separate from verified
structured inventory. No live CRM writes, customer messages, merge or deployment
occurred.
