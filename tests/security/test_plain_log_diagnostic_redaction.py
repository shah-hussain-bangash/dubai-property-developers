"""Configured plain-text logging must redact diagnostics added by the formatter."""

import io
import json
import logging
import secrets
import sys
import unittest
from unittest.mock import patch

from core.observability.logging import configure_logging
from core.security.redaction import REDACTED


class PlainTextDiagnosticRedactionTests(unittest.TestCase):
    def setUp(self):
        self.root = logging.getLogger()
        self.saved_handlers, self.saved_level = list(self.root.handlers), self.root.level

    def tearDown(self):
        for handler in self.root.handlers:
            if handler not in self.saved_handlers:
                handler.close()
        self.root.handlers = self.saved_handlers
        self.root.setLevel(self.saved_level)

    def render(self, record, *, mask_pii=True, json_output=False):
        stream = io.StringIO()
        with patch("sys.stdout", stream):
            configure_logging(mask_pii=mask_pii, json_output=json_output)
        self.root.handlers[0].handle(record)
        return stream.getvalue()

    def exception_record(self, detail):
        try:
            raise ValueError(detail)
        except ValueError:
            return logging.LogRecord(
                "fixture", logging.ERROR, __file__, 1, "request failed", (), sys.exc_info()
            )

    def test_plain_traceback_redacts_credentials_but_preserves_error_context(self):
        token, password = secrets.token_hex(12) + "+/==", secrets.token_hex(16)
        record = self.exception_record(f"Bearer {token}; rediss://:{password}@cache.example/0")
        output = self.render(record, mask_pii=False)
        self.assertNotIn(token, output)
        self.assertNotIn(password, output)
        self.assertIn(REDACTED, output)
        self.assertIn("ValueError", output)
        self.assertIn("cache.example/0", output)
        self.assertIn("request failed", output)

    def test_cached_exception_from_another_formatter_is_redacted(self):
        token = secrets.token_hex(16)
        record = self.exception_record(f"Bearer {token}")
        logging.Formatter().format(record)
        self.assertIn(token, record.exc_text)
        output = self.render(record, mask_pii=False)
        self.assertNotIn(token, output)
        self.assertIn(REDACTED, output)

    def test_stack_diagnostics_are_redacted(self):
        token = secrets.token_hex(16)
        record = logging.LogRecord("fixture", logging.INFO, __file__, 1, "diagnostic", (), None)
        record.stack_info = f"Stack (fixture): Bearer {token}"
        output = self.render(record, mask_pii=False)
        self.assertNotIn(token, output)
        self.assertIn("Stack (fixture):", output)
        self.assertIn(REDACTED, output)

    def test_pii_preference_applies_to_plain_exception_text(self):
        token = secrets.token_hex(16)
        for mask_pii in (False, True):
            with self.subTest(mask_pii=mask_pii):
                record = self.exception_record(f"demo.person@example.com Bearer {token}")
                output = self.render(record, mask_pii=mask_pii)
                self.assertNotIn(token, output)
                if mask_pii:
                    self.assertNotIn("demo.person@example.com", output)
                    self.assertIn("d***@example.com", output)
                else:
                    self.assertIn("demo.person@example.com", output)

    def test_json_exception_redaction_remains_valid(self):
        token = secrets.token_hex(16)
        record = self.exception_record(f"Bearer {token}")
        output = self.render(record, json_output=True)
        self.assertNotIn(token, output)
        payload = json.loads(output)
        self.assertEqual(payload["message"], "request failed")
        self.assertIn(REDACTED, payload["exception"])
