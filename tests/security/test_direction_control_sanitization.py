"""Invisible bidi controls are removed while ordinary Arabic text is retained."""

import unittest

from core.policies.prompt_safety import ContentSource, UntrustedContent
from core.security.sanitization import sanitize_name, sanitize_text


class DirectionControlSanitizationTests(unittest.TestCase):
    def test_direction_isolates_are_removed_from_text_and_names(self):
        for control in ("\u2066", "\u2067", "\u2068", "\u2069"):
            for value in (control + "Fixture", "Fix" + control + "ture", "Fixture" + control):
                with self.subTest(control=ascii(control), value=ascii(value)):
                    self.assertEqual(sanitize_text(value), "Fixture")
                    self.assertEqual(sanitize_name(value), "Fixture")

    def test_arabic_letter_mark_is_removed_without_removing_arabic_letters(self):
        value = "\u061cدبي\u061c"
        self.assertEqual(sanitize_text(value), "دبي")
        self.assertEqual(sanitize_name(value), "دبي")

    def test_existing_controls_whitespace_and_normalization_keep_working(self):
        controls = "\u200b\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2060\ufeff"
        self.assertEqual(sanitize_text(controls + "  Fixture\t text\x00  "), "Fixture text")
        self.assertEqual(sanitize_text("دبي، مرحباً"), "دبي، مرحباً")
        self.assertEqual(sanitize_text("\uff26\uff49\uff58\uff54\uff55\uff52\uff45"), "Fixture")
        self.assertEqual(sanitize_text("Fixture\ntext"), "Fixture\ntext")
        self.assertEqual(sanitize_text("Fixture", max_length=3), "Fix")

    def test_prompt_data_cannot_retain_direction_controls(self):
        value = "\u2067Fixture\u2069 \u061cدبي"
        rendered = UntrustedContent(ContentSource.CUSTOMER_MESSAGE, value).render()

        self.assertEqual(
            rendered,
            '<untrusted source="customer_message">\nFixture دبي\n</untrusted>',
        )
        for control in ("\u2067", "\u2069", "\u061c"):
            self.assertNotIn(control, rendered)
