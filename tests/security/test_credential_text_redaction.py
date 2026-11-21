"""Credential redaction covers bearer token syntax and Redis connection URLs."""

import json
import logging
import secrets
import unittest

from core.observability.logging import JsonFormatter, RedactionFilter
from core.security.redaction import REDACTED, redact_text, redact_value


class CredentialTextRedactionTests(unittest.TestCase):
    def test_complete_bearer_tokens_are_redacted_without_consuming_delimiters(self):
        for token in ("x", "short", secrets.token_hex(12) + "._~+/-=="):
            for scheme in ("Bearer", "bearer", "BEARER"):
                with self.subTest(token=token, scheme=scheme):
                    text = f'header="{scheme} {token}", status=401'
                    self.assertEqual(
                        redact_text(text, mask_pii=False),
                        f'header="{REDACTED}", status=401',
                    )

    def test_redis_passwords_are_redacted_with_tls_and_empty_username(self):
        password = secrets.token_hex(16)
        for scheme in ("redis", "rediss", "REDISS"):
            for username in ("demo", ""):
                with self.subTest(scheme=scheme, username=username):
                    text = f"cache={scheme}://{username}:{password}@cache.example:6379/0"
                    self.assertEqual(
                        redact_text(text, mask_pii=False),
                        f"cache={REDACTED}cache.example:6379/0",
                    )

    def test_postgres_credentials_and_unrelated_values_keep_existing_behavior(self):
        password = secrets.token_hex(16)
        for scheme in ("postgres", "postgresql", "postgresql+asyncpg"):
            with self.subTest(scheme=scheme):
                text = f"{scheme}://demo:{password}@db.example:5432/catalog"
                self.assertEqual(
                    redact_text(text, mask_pii=False),
                    f"{REDACTED}db.example:5432/catalog",
                )
        text = "on 2026-11-21 budget 1500000 AED https://example.com/property/123"
        self.assertEqual(redact_text(text), text)

    def test_nested_redaction_is_independent_of_pii_masking_and_does_not_mutate(self):
        token, password = secrets.token_hex(12) + "+/==", secrets.token_hex(16)
        source = {"events": [{"detail": f"Bearer {token}; rediss://:{password}@cache.example/0"}]}
        for mask_pii in (False, True):
            with self.subTest(mask_pii=mask_pii):
                self.assertEqual(
                    redact_value(source, mask_pii=mask_pii),
                    {"events": [{"detail": f"{REDACTED}; {REDACTED}cache.example/0"}]},
                )
        self.assertIn(token, source["events"][0]["detail"])
        self.assertIn(password, source["events"][0]["detail"])

    def test_structured_log_message_extra_and_exception_are_redacted(self):
        token, password = secrets.token_hex(12) + "~+/==", secrets.token_hex(16)
        detail = f"Bearer {token}; rediss://:{password}@cache.example/0"
        error = ValueError(detail)
        record = logging.LogRecord(
            "fixture",
            logging.ERROR,
            __file__,
            1,
            "request failed: %s",
            (detail,),
            (ValueError, error, None),
        )
        record.detail = detail
        record.request_id = "fixture-request-123"
        RedactionFilter(mask_pii=False).filter(record)
        rendered = JsonFormatter().format(record)
        self.assertNotIn(token, rendered)
        self.assertNotIn(password, rendered)
        payload = json.loads(rendered)
        self.assertEqual(payload["request_id"], "fixture-request-123")
        self.assertIn("cache.example/0", payload["detail"])
        for field in ("message", "detail", "exception"):
            self.assertIn(REDACTED, payload[field])
