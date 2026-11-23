"""Immutable sets receive the same secret and PII redaction as mutable sets."""

import json
import logging
import secrets
import unittest

from core.events.audit import AuditEvent, InMemoryAuditSink
from core.observability.logging import JsonFormatter, RedactionFilter
from core.security.redaction import REDACTED, redact_value


class FrozenSetRedactionTests(unittest.IsolatedAsyncioTestCase):
    def test_nested_frozen_sets_redact_secrets_without_mutating_input(self):
        token = secrets.token_hex(16)
        original = {"details": [frozenset({(f"Bearer {token}", "fixture-safe")})]}

        redacted = redact_value(original)

        self.assertEqual(redacted, {"details": [[[REDACTED, "fixture-safe"]]]})
        self.assertIn(token, repr(original))
        self.assertNotIn(token, repr(redacted))

    def test_pii_masking_option_preserves_secret_redaction(self):
        token = secrets.token_hex(16)
        original = frozenset({"fixture.person@example.com", f"Bearer {token}"})

        masked = redact_value(original)
        unmasked = redact_value(original, mask_pii=False)

        self.assertCountEqual(masked, ["f***@example.com", REDACTED])
        self.assertCountEqual(unmasked, ["fixture.person@example.com", REDACTED])
        self.assertNotIn(token, repr(masked))
        self.assertNotIn(token, repr(unmasked))

    def test_depth_limit_applies_inside_nested_frozen_sets(self):
        original = "fixture-depth-value"
        for _ in range(10):
            original = frozenset({original})

        redacted = redact_value(original)

        self.assertNotIn("fixture-depth-value", repr(redacted))
        self.assertIn(REDACTED, repr(redacted))

    def test_empty_and_safe_frozen_sets_use_existing_collection_output(self):
        self.assertEqual(redact_value(frozenset()), [])
        self.assertCountEqual(
            redact_value(frozenset({"fixture-a", "fixture-b"})), ["fixture-a", "fixture-b"]
        )

    def test_structured_log_extras_do_not_expose_frozen_set_credentials(self):
        token = secrets.token_hex(16)
        record = logging.LogRecord("fixture", logging.INFO, __file__, 1, "fixture", (), None)
        record.details = {"values": frozenset({f"Bearer {token}"})}
        RedactionFilter().filter(record)

        rendered = JsonFormatter().format(record)

        self.assertNotIn(token, rendered)
        self.assertEqual(json.loads(rendered)["details"], {"values": [REDACTED]})

    async def test_audit_details_redact_frozen_set_credentials(self):
        token = secrets.token_hex(16)
        event = AuditEvent(
            tenant_id="fixture",
            actor="fixture-actor",
            action="fixture-action",
            resource_type="fixture",
            outcome="denied",
            details={"values": frozenset({f"Bearer {token}"})},
        )
        sink = InMemoryAuditSink()

        await sink.record(event)

        self.assertEqual(sink.events[0].details, {"values": [REDACTED]})
        self.assertNotIn(token, sink.events[0].model_dump_json())
        self.assertIn(token, repr(event.details))
