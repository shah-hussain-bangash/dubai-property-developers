# Explicit consent at delivery

Verified locally on 24 November 2026 against PR #87 revision
`933eecfb7e7ecd976fa1bb7df3247b60a6ac1711` plus this change.

## Observed blocker

Email marketing and WhatsApp tools checked consent using Python truthiness.
Non-empty strings such as `"false"`, numbers such as `1`, and non-empty objects
could therefore pass the send boundary without a boolean opt-in. The current
WhatsApp conversation-state check had the same issue. Separately, standalone
email execution did not call validation, allowing even boolean false marketing
consent to reach its mock sender. The first regression run reported **22 failed
and ten passed**.

## Change and verification

WhatsApp payload and current conversation consent now require the boolean `True`.
Marketing email consent requires the same, and email validates immediately before
calling its sender, including standalone execution. Non-marketing email retains
its existing consent policy. Typed agent inputs retain their existing parsing;
these checks protect the raw tool and stored-state boundaries.

All **32 new regression cases passed**. They cover false, null, integer, string
and object values through gateway and standalone entry points, current stored
consent on an already approved WhatsApp reply, and valid marketing/non-marketing
email controls. Denied sends leave mock outboxes empty; gateway validation also
creates no approval request. The focused consent, delivery-key, source-approval
and opt-out suites passed **99 tests**.

The full local Python 3.14 suite reported **1,638 passed, 155 skipped, four existing
expected failures and 662 passing subtests**. Three existing dependency/configuration
warnings remain. Integration skips require explicitly enabled local services;
expected failures cover existing recovery/fencing gaps. Ruff, formatting checks
and mypy for seven email/WhatsApp source files passed.

Reproduce using development dependencies:

```text
python -m pytest tests/security/test_explicit_delivery_consent.py tests/security/test_delivery_key_isolation.py tests/security/test_whatsapp_optout_races.py tests/security/test_source_bound_approvals.py -q
python -m pytest -q
python -m mypy tools/email tools/whatsapp
```

All deliveries use fictional recipients and mock providers. This does not add a
durable contact-wide consent registry, synchronize CRM consent, verify live
providers, or cancel a provider call already in flight. No merge, deployment or
live message occurred.
