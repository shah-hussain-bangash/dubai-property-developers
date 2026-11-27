# Strict JSON customer approval on source imports

Verified locally on 27 November 2026 against parent
`5cd218fb2ed44ab9e7a9bf8137335b04309e8ccc` plus this fix in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. All
source text and identities in the tests are fictional; API providers are mocked.
No hosted/browser acceptance or live delivery is claimed.

## Observed blocker and fix

The JSON source-input model used a coercing boolean for `customer_safe`, while
explicit saved-source reviews already used a strict boolean. The real local API
accepted `"yes"` and numeric `1` and persisted `customer_safe: 1`. Malformed JSON
approval types could therefore change customer eligibility instead of being
rejected. These requests still required the existing authorized write role; this
was a type/approval-boundary inconsistency, not a role or tenant permission bypass.

JSON text and website imports now require literal boolean `true` or `false` when
customer approval is supplied. Strings, numbers, null, arrays and objects are
rejected with HTTP 422 before source persistence. Invalid website flags are rejected
before website ingestion/fetch is called. Omission still defaults to false, keeping
new sources staff-only. Valid false/true re-imports keep their existing deliberate
approval-update behavior. Approved/current own sources remain customer-eligible;
staff-only sources remain available only in staff retrieval.

This is an intentional compatibility tightening for JSON callers: replace formerly
coerced values such as `1`, `0`, `"yes"`, `"true"` and `"false"` with actual JSON
booleans. For example:

```json
{
  "kind": "text",
  "title": "Fictional approved policy",
  "text": "Fictional approvalmarker gardens allow two visits.",
  "customer_safe": true
}
```

The dashboard already sends booleans for JSON sources, so its wire payload is
unchanged. Raw PDF/text/Markdown upload query parameters retain their existing
transport contract: `customer_safe=true` explicitly approves, while false/omitted
is staff-only. Query parameters are strings and are not the JSON-body field.
Existing stored sources are not migrated or automatically revoked. No source IDs,
review dates/history, storage schema, owner/role policy, retrieval or delivery
behavior changes beyond rejecting malformed JSON approval types.

Strict typing does not prove a human reviewed a source or that its facts are
correct. The existing authorized source-upload/review process remains responsible
for that decision.

## Reproduce

1. Use a disposable local authenticated mock-provider API and Document Agent.
   Import the fictional text above using boolean true. Confirm its source is
   customer-approved and the customer preview quotes only its own source.
2. Re-submit the same source with each invalid value: `0`, `1`, `"yes"`, `"true"`,
   `"false"`, null, object and array. Each returns 422. Read the list after every
   rejection: the original metadata and approval remain exactly unchanged. The
   matching source in another organization is also unchanged.
3. Import with boolean false: it remains available to staff but customer retrieval
   abstains. Import again with boolean true: customer eligibility returns. A new
   source with approval omitted defaults to staff-only.
4. Submit a website import with invalid approval. Confirm the mocked ingestion
   function is not called and no source is stored. A valid boolean-true website
   request still uses the established ingestion path.
5. Upload raw text using the existing true, false and omitted query forms: their
   stored flags remain 1, 0 and 0, respectively. Existing role/organization checks
   and private/no-store read behavior remain in force.

[Structured local API evidence](knowledge-json-approval-local-2026-11-27.json)
records eight rejections with unchanged source state, valid boolean customer/staff
answers and the omitted-approval default. Only deliberate valid imports change
source flags; the rejected requests write nothing and create no review events.

## Validation

Two new API regressions reproduced public-source approval from non-boolean values
before the fix and now pass. Thirteen parameterized agent cases verify all malformed
values, unchanged own/foreign sources, valid true/false/default behavior and actual
staff/customer answers. Website pre-fetch rejection and raw-upload compatibility
add two cases: 17 new cases total. The focused run passes 41 API tests.

- Full local backend: 2,544 passed, 156 skipped, four existing expected failures
  and 662 passing subtests. Database integration prerequisites and the Windows
  Unix-permission skip remain; disposable database services run separately in CI.
- Ruff, Python formatting and focused mypy passed. Dashboard code is unchanged;
  its suite is verified by CI rather than repeated locally for this API-only fix.
- Dashboard code is unchanged; its existing suite runs in GitHub CI.
- No live writes, customer messages, merge or deployment are included. Hosted
  verification remains pending hosting access recovery.
