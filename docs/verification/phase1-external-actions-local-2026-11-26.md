# Phase 1 external action review and CRM acknowledgement fix

Local verification on 26 November 2026. Parent revision
`c517a6cb584d89975c9a51bf45435db9b0cb348c`, plus this change in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
All provider requests use mocks or HTTP mock transports. No live account is used.

## Confirmed blocker and fix

The HTTP CRM adapter converted creation response IDs with `str(body["id"])`.
For example, a synthetic `{"id": null}` acknowledgement returned the literal
string `"None"`. A numeric or boolean ID was similarly coerced. Lead and note
tools could report and cache invalid creation identities as successful results.
This is a reproduced synthetic response defect, not evidence of a live incident.

Lead/note HTTP acknowledgements now require an object containing a string ID
that meets the existing bounded literal CRM record-ID contract. The tools also
validate returned IDs before the gateway can cache success, covering alternative
client implementations. IDs are preserved without normalization. Invalid
acknowledgements produce a bounded validation error and are not retried inside
the HTTP client.

The provider may have performed the write before returning a malformed response.
Rejection does not undo that write or prove that a subsequent user retry is safe.
Live use still needs provider-specific reconciliation and retry validation.

## Review scope

- CRM tool account ownership, creation inputs, lookup ambiguity, record IDs and
  detached mock records; CRM HTTP and mock adapters.
- Calendar ownership, explicit timestamp offsets and contextual retry keys;
  calendar remains mock-only.
- WhatsApp opt-in, current conversation opt-out, recipient matching and service
  window checks; marketing email requires explicit recorded marketing consent.
- Shared HTTP origin/redirect restrictions and bounded retry policy; n8n webhook
  paths cannot escape the configured webhook prefix through URL syntax.

The existing 343 selected checks passed before the fix. No additional confirmed
blocker was found in this review group beyond malformed creation acknowledgements.
This is not full PR approval or live provider certification.

## Regression evidence

New file: `tests/security/test_crm_creation_response_identity.py`.

- Before the fix: **40 failed, three passed**.
- After the fix: **43 cases pass** within **386 focused passing tests**, with
  **44 passing subtests**. One existing Starlette TestClient/httpx deprecation
  warning remains.
- Cases cover malformed body types, absent/null/boolean/numeric/empty/unsafe IDs,
  valid literal IDs, lead and note creation, no automatic retry on malformed
  acknowledgements, failed-result exclusion from cache and valid result replay.
- Ruff checks, formatting and focused mypy pass for the changed source files.
- The complete backend run passes **2,200 tests**, with 155 integration-dependent
  skips, four existing expected failures and 662 passing subtests in 52.51 seconds.
  Three warnings remain. Expected failures document the existing cross-system
  recovery/fencing gap; they are not counted as passes.

Run from the source root with the project virtual environment:

```text
python -m pytest tests/security/test_crm_creation_response_identity.py -q -p no:cacheprovider --basetemp=../fresh-crm-response-check
python -m pytest tests/security/test_crm_creation_response_identity.py tests/security/test_crm_account_binding.py tests/security/test_crm_ambiguous_matches.py tests/security/test_crm_creation_inputs.py tests/security/test_crm_creation_retry_conflicts.py tests/security/test_crm_lookup_record_validation.py tests/security/test_crm_readonly_identity.py tests/security/test_crm_record_id_paths.py tests/security/test_crm_record_snapshots.py tests/security/test_calendar_booking_boundaries.py tests/security/test_delivery_key_isolation.py tests/security/test_explicit_delivery_consent.py tests/security/test_whatsapp_optout_races.py tests/security/test_integration_redirect_rejection.py tests/security/test_n8n_webhook_paths.py tests/unit/test_retry_policy_boundaries.py -q
python -m pytest -q -p no:cacheprovider --basetemp=../fresh-full-backend-check
python -m ruff check integrations/espocrm/client.py tools/crm/tools.py tests/security/test_crm_creation_response_identity.py
python -m ruff format --check integrations/espocrm/client.py tools/crm/tools.py tests/security/test_crm_creation_response_identity.py
python -m mypy integrations/espocrm/client.py tools/crm/tools.py
```

The local runs used Python 3.14 and disposable local test directories.

## Remaining release conditions

HTTP adapters remain unverified against provider sandbox accounts. Supplying an
idempotency header does not establish provider deduplication or distributed
exactly-once delivery. CRM note creation has no provider retry key. Consent is
not a durable contact-wide registry; Follow-Up uses its typed consent input.
No new scheduler, provider configuration or booking permission is added.

No merge, deployment, real CRM write, calendar booking or customer communication
is performed. The hosted revision and synthetic operator access remain unconfirmed.
