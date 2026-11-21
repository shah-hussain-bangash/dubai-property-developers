"""Malformed password records must fail closed without weakening the digest."""

import base64
import secrets
import unittest
from unittest.mock import patch

from core.security.passwords import hash_password, verify_password


class PasswordRecordValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = secrets.token_urlsafe(24)
        cls.encoded = hash_password(cls.password)

    def test_generated_hash_accepts_correct_password_only(self):
        self.assertTrue(verify_password(self.password, self.encoded))
        self.assertFalse(verify_password(self.password + "-wrong", self.encoded))

    def test_shortened_digest_cannot_weaken_password_verification(self):
        fields = self.encoded.split("$")
        digest = base64.b64decode(fields[-1])
        for length in (1, 16, 32, 63):
            with self.subTest(length=length):
                fields[-1] = base64.b64encode(digest[:length]).decode()
                self.assertFalse(verify_password(self.password, "$".join(fields)))

    def test_invalid_base64_characters_are_rejected(self):
        for index in (4, 5):
            for extra in ("!", " ", "\n", "é"):
                with self.subTest(index=index, extra=extra):
                    fields = self.encoded.split("$")
                    fields[index] += extra
                    self.assertFalse(verify_password(self.password, "$".join(fields)))

    def test_invalid_record_lengths_are_rejected_before_scrypt(self):
        for index, size in ((4, 0), (4, 15), (4, 17), (5, 0), (5, 63), (5, 65)):
            with self.subTest(index=index, size=size):
                fields = self.encoded.split("$")
                fields[index] = base64.b64encode(b"x" * size).decode()
                with patch("core.security.passwords.hashlib.scrypt") as scrypt:
                    self.assertFalse(verify_password(self.password, "$".join(fields)))
                    scrypt.assert_not_called()

    def test_overflowing_cost_parameters_are_rejected(self):
        for index in (1, 2, 3):
            with self.subTest(index=index):
                fields = self.encoded.split("$")
                fields[index] = "9" * 400
                self.assertFalse(verify_password(self.password, "$".join(fields)))

    def test_stored_cost_parameters_remain_supported(self):
        with patch("core.security.passwords._N", 2**13):
            older = hash_password(self.password)
        self.assertTrue(verify_password(self.password, older))
        self.assertFalse(verify_password(self.password + "-wrong", older))
