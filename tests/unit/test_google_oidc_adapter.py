"""Synthetic adapter tests. Real Google signatures and callbacks are not tested."""

import runpy
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[2]
namespace = runpy.run_path(str(ROOT / "core/security/google_oidc.py"))
GoogleOIDC = namespace["GoogleOIDC"]
GoogleSignInError = namespace["GoogleSignInError"]
CLIENT = "synthetic-client.apps.googleusercontent.com"
CALLBACK = "https://app.example.com/api/auth/google/callback"


def adapter(**overrides):
    config = {
        "client_id": CLIENT,
        "client_secret": "synthetic-test-secret",
        "redirect_uri": CALLBACK,
    }
    config.update(overrides)
    return GoogleOIDC(**config)


def claims(**overrides):
    values = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT,
        "sub": "synthetic-google-subject",
        "email": "user@example.com",
        "email_verified": True,
        "name": "Example User",
        "exp": int(time.time()) + 300,
    }
    values.update(overrides)
    return values


def request():
    return SimpleNamespace(scope={"session": {}})


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_real_authlib_client_constructs_without_network(self):
        instance = adapter()
        self.assertEqual(instance._client.name, "google")

    async def test_start_uses_fixed_callback_and_fresh_nonce(self):
        instance = adapter()
        remote = SimpleNamespace(authorize_redirect=AsyncMock(return_value="redirect"))
        instance._client = remote
        self.assertEqual(await instance.start(request()), "redirect")
        await instance.start(request())
        calls = remote.authorize_redirect.await_args_list
        self.assertEqual(calls[0].args[1], CALLBACK)
        self.assertGreaterEqual(len(calls[0].kwargs["nonce"]), 32)
        self.assertNotEqual(calls[0].kwargs["nonce"], calls[1].kwargs["nonce"])

    async def test_session_required(self):
        instance = adapter()
        with self.assertRaises(GoogleSignInError):
            await instance.start(SimpleNamespace(scope={}))
        with self.assertRaises(GoogleSignInError):
            await instance.complete(SimpleNamespace(scope={}))

    async def test_verified_claims_return_external_identity_only(self):
        instance = adapter()
        remote = SimpleNamespace(
            authorize_access_token=AsyncMock(
                return_value={"userinfo": claims(), "access_token": "private-token"}
            )
        )
        instance._client = remote
        result = await instance.complete(request())
        remote.authorize_access_token.assert_awaited_once()
        self.assertEqual(
            set(result),
            {
                "issuer",
                "subject",
                "email",
                "full_name",
            },
        )
        self.assertEqual(result["subject"], "synthetic-google-subject")
        self.assertNotIn("private-token", str(result))
        self.assertNotIn("approval_status", result)

    async def test_invalid_claims_rejected(self):
        invalid = [
            {"iss": "https://attacker.example"},
            {"aud": "different-client"},
            {"aud": [CLIENT, "other-client"]},
            {"azp": "different-client"},
            {"exp": int(time.time()) - 10},
            {"exp": True},
            {"exp": float("inf")},
            {"sub": ""},
            {"sub": "subject\n"},
            {"email_verified": False},
            {"email_verified": "true"},
            {"email": "invalid-email"},
        ]
        for values in invalid:
            with self.subTest(values=values):
                instance = adapter()
                instance._client = SimpleNamespace(
                    authorize_access_token=AsyncMock(return_value={"userinfo": claims(**values)})
                )
                with self.assertRaises(GoogleSignInError):
                    await instance.complete(request())

    async def test_provider_failure_is_sanitized(self):
        instance = adapter()
        instance._client = SimpleNamespace(
            authorize_access_token=AsyncMock(side_effect=ValueError("private token diagnostic"))
        )
        with self.assertRaises(GoogleSignInError) as caught:
            await instance.complete(request())
        self.assertNotIn("private", str(caught.exception))

    async def test_missing_verified_userinfo_rejected(self):
        instance = adapter()
        instance._client = SimpleNamespace(
            authorize_access_token=AsyncMock(return_value={"id_token": "raw-token"})
        )
        with self.assertRaises(GoogleSignInError):
            await instance.complete(request())

    async def test_callback_configuration_restricted(self):
        for uri in (
            "http://app.example.com/callback",
            "https://user:password@app.example.com/callback",
            "https://app.example.com/callback?next=elsewhere",
            "https://app.example.com/callback#fragment",
        ):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                adapter(redirect_uri=uri)
        adapter(
            redirect_uri="http://localhost:8000/api/auth/google/callback",
            allow_local_http=True,
        )
        with self.assertRaises(ValueError):
            adapter(
                redirect_uri="http://attacker.example/callback",
                allow_local_http=True,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
