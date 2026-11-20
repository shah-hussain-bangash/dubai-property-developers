"""Real synthetic-password hashing plus fake-database registration tests."""
import base64
import runpy
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from sqlalchemy.dialects import postgresql

ROOT = Path(__file__).resolve().parents[2]
credentials = runpy.run_path(str(ROOT / "core/security/account_credentials.py"))
registration = runpy.run_path(
    str(ROOT / "database/repositories/account_registration.py")
)
hash_password = credentials["hash_password"]
verify_password = credentials["verify_password"]
Registration = registration["PendingAccountRegistration"]

def encoded(salt=b"\0" * 16, key=b"\0" * 64):
    return "$".join([
        "scrypt", "16384", "8", "1",
        base64.b64encode(salt).decode(),
        base64.b64encode(key).decode(),
    ])

class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_real_scrypt_roundtrip_and_wrong_password(self):
        value = hash_password("synthetic-password")
        self.assertLessEqual(len(value), 255)
        self.assertTrue(verify_password("synthetic-password", value))
        self.assertFalse(verify_password("different-password", value))

    async def test_malformed_hashes_rejected_before_scrypt(self):
        normal = encoded()
        fields = normal.split("$")
        bad_salt = fields.copy()
        bad_salt[4] = bad_salt[4][:21] + "B=="
        bad_key = fields.copy()
        bad_key[5] = bad_key[5][:85] + "B=="
        cases = [
            normal.replace("$16384$", "$016384$"),
            normal.replace("$16384$", "$0$"),
            normal.replace("$16384$", "$1073741824$"),
            normal.replace("$8$1$", "$9$1$"),
            normal.replace("$8$1$", "$8$2$"),
            normal.replace("scrypt$", "other$", 1),
            "$".join(fields[:-1]),
            normal + "$extra",
            encoded(salt=b"\0" * 17),
            encoded(key=b"\0" * 65),
            "$".join(bad_salt),
            "$".join(bad_key),
            "$".join(fields[:4] + ["", fields[5]]),
            "$".join(fields[:5] + [""]),
            "x" * 257,
            None,
        ]
        with patch.object(
            credentials["hashlib"], "scrypt",
            side_effect=AssertionError("malformed input reached scrypt"),
        ) as kdf:
            for value in cases:
                with self.subTest(case_type=type(value).__name__):
                    self.assertFalse(verify_password("synthetic-password", value))
            kdf.assert_not_called()

    async def test_invalid_password_inputs_do_not_reach_scrypt(self):
        with patch.object(credentials["hashlib"], "scrypt") as kdf:
            for password in (None, 123, "x" * 1025, "\ud800" * 12):
                self.assertFalse(verify_password(password, encoded()))
                with self.assertRaises(ValueError):
                    hash_password(password)
            with self.assertRaises(ValueError):
                hash_password("short")
            kdf.assert_not_called()

    async def test_supported_parameters_are_fixed(self):
        with patch.object(
            credentials["hashlib"], "scrypt", return_value=b"\0" * 64,
        ) as kdf:
            self.assertTrue(verify_password("synthetic-password", encoded()))
            arguments = kdf.call_args.kwargs
            self.assertEqual(arguments["n"], 16384)
            self.assertEqual(arguments["r"], 8)
            self.assertEqual(arguments["p"], 1)
            self.assertEqual(arguments["dklen"], 64)
            self.assertEqual(arguments["maxmem"], 33554432)

    async def test_registration_accepts_real_hasher_without_plaintext_storage(self):
        organization = UUID(int=1)
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        transaction = MagicMock()
        transaction.__aenter__ = AsyncMock()
        transaction.__aexit__ = AsyncMock(return_value=False)
        session.begin.return_value = transaction
        responses = []
        for value in ({"id": organization}, None, None, None):
            response = MagicMock()
            response.mappings.return_value.first.return_value = value
            responses.append(response)
        session.execute = AsyncMock(side_effect=responses)
        service = Registration(lambda: session, password_hasher=hash_password)
        result = await service.register_password(
            organization, email="user@example.com",
            full_name="Example User", password="synthetic-password",
        )
        self.assertEqual(result["approval_status"], "pending")
        statement = session.execute.await_args_list[2].args[0]
        parameters = statement.compile(dialect=postgresql.dialect()).params
        self.assertNotIn("synthetic-password", parameters.values())
        self.assertTrue(
            verify_password("synthetic-password", parameters["password_hash"])
        )
        self.assertNotIn("password_hash", result)

if __name__ == "__main__":
    unittest.main(verbosity=2)
