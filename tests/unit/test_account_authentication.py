"""Authentication orchestration tests; fake database and provider callbacks."""

import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

ROOT = Path(__file__).resolve().parents[2]
module = runpy.run_path(str(ROOT / "database/repositories/account_authentication.py"))
credentials = runpy.run_path(str(ROOT / "core/security/account_credentials.py"))
Authentication = module["AccountAuthentication"]
ORG, USER, OTHER = [UUID(int=i) for i in (1, 2, 3)]


def row(**overrides):
    value = {
        "id": USER,
        "organization_id": ORG,
        "password_hash": "synthetic-stored-hash",
        "is_active": True,
        "approval_status": "pending",
    }
    value.update(overrides)
    return value


def setup(value, *, verifier=None, dummy_hash="synthetic-dummy-hash"):
    response = MagicMock()
    response.mappings.return_value.first.return_value = value
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock()
    transaction.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value = transaction
    session.execute = AsyncMock(return_value=response)
    registration = SimpleNamespace(
        register_password=AsyncMock(return_value={"approval_status": "pending"}),
        google_account=AsyncMock(
            return_value={
                "account_id": USER,
                "organization_id": ORG,
                "approval_status": "pending",
            }
        ),
    )
    sessions = SimpleNamespace(
        issue_authenticated=AsyncMock(return_value="synthetic-session-result"),
        revoke=AsyncMock(return_value=True),
    )
    google = SimpleNamespace(
        complete=AsyncMock(
            return_value={
                "issuer": "https://accounts.google.com",
                "subject": "synthetic-subject",
                "email": "user@example.com",
                "full_name": "Example User",
            }
        )
    )
    verifier = verifier if verifier is not None else MagicMock(return_value=True)
    service = Authentication(
        lambda: session,
        password_verifier=verifier,
        dummy_hash=dummy_hash,
        registration_service=registration,
        session_service=sessions,
        google_provider=google,
    )
    return service, session, verifier, registration, sessions, google


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_password_login_verifies_before_session_issue(self):
        service, session, verifier, _registration, sessions, _google = setup(row())
        result = await service.login_password(
            ORG,
            email="user@example.com",
            password="synthetic-password",
        )
        self.assertEqual(result, "synthetic-session-result")
        verifier.assert_called_once_with(
            "synthetic-password",
            "synthetic-stored-hash",
        )
        sessions.issue_authenticated.assert_awaited_once_with(
            USER,
            ORG,
            auth_method="password",
        )
        sql = str(
            session.execute.await_args.args[0].compile(
                dialect=postgresql.dialect(),
            )
        )
        self.assertIn("users.organization_id =", sql)
        self.assertIn("organizations.is_active IS true", sql)
        self.assertIn("FOR SHARE", sql)

    async def test_missing_or_google_only_account_uses_dummy_hash(self):
        for value in (None, row(password_hash=None)):
            with self.subTest(value_present=value is not None):
                service, _session, verifier, _registration, sessions, _google = setup(value)
                with self.assertRaises(HTTPException) as caught:
                    await service.login_password(
                        ORG,
                        email="user@example.com",
                        password="synthetic-password",
                    )
                self.assertEqual(caught.exception.status_code, 401)
                verifier.assert_called_once_with(
                    "synthetic-password",
                    "synthetic-dummy-hash",
                )
                sessions.issue_authenticated.assert_not_awaited()

    async def test_wrong_password_rejected_or_inactive_account_denied(self):
        cases = [
            (row(), False),
            (row(approval_status="rejected"), True),
            (row(approval_status=None), True),
            (row(is_active=False), True),
        ]
        for value, valid in cases:
            with self.subTest(status=value["approval_status"], valid=valid):
                service, _session, _verifier, _registration, sessions, _google = setup(
                    value,
                    verifier=MagicMock(return_value=valid),
                )
                with self.assertRaises(HTTPException) as caught:
                    await service.login_password(
                        ORG,
                        email="user@example.com",
                        password="synthetic-password",
                    )
                self.assertEqual(caught.exception.detail, "invalid sign-in")
                sessions.issue_authenticated.assert_not_awaited()

    async def test_real_password_verifier_integrates(self):
        encoded = credentials["hash_password"]("synthetic-password")
        service, _session, _verifier, _registration, sessions, _google = setup(
            row(password_hash=encoded),
            verifier=credentials["verify_password"],
            dummy_hash=encoded,
        )
        await service.login_password(
            ORG,
            email="user@example.com",
            password="synthetic-password",
        )
        sessions.issue_authenticated.assert_awaited_once()

    async def test_google_pipeline_preserves_pending_status(self):
        service, session, _verifier, registration, sessions, google = setup(None)
        request = object()
        await service.login_google(ORG, request=request)
        google.complete.assert_awaited_once_with(request)
        registration.google_account.assert_awaited_once_with(
            ORG,
            verified_identity=google.complete.return_value,
        )
        sessions.issue_authenticated.assert_awaited_once_with(
            USER,
            ORG,
            auth_method="google",
        )
        session.execute.assert_not_awaited()

    async def test_google_failure_or_foreign_account_does_not_issue_session(self):
        service, _session, _verifier, registration, sessions, google = setup(None)
        google.complete.side_effect = ValueError("synthetic provider failure")
        with self.assertRaises(ValueError):
            await service.login_google(ORG, request=object())
        registration.google_account.assert_not_awaited()
        sessions.issue_authenticated.assert_not_awaited()

        service, _session, _verifier, registration, sessions, google = setup(None)
        registration.google_account.return_value = {
            "account_id": USER,
            "organization_id": OTHER,
        }
        with self.assertRaises(HTTPException):
            await service.login_google(ORG, request=object())
        sessions.issue_authenticated.assert_not_awaited()

    async def test_registration_does_not_issue_session_automatically(self):
        service, _session, _verifier, registration, sessions, _google = setup(None)
        result = await service.register_password(
            ORG,
            email="user@example.com",
            full_name="Example User",
            password="synthetic-password",
        )
        self.assertEqual(result["approval_status"], "pending")
        registration.register_password.assert_awaited_once()
        sessions.issue_authenticated.assert_not_awaited()

    async def test_logout_delegates_revocation(self):
        service, _session, _verifier, _registration, sessions, _google = setup(None)
        self.assertTrue(await service.logout("synthetic-session-result"))
        sessions.revoke.assert_awaited_once_with("synthetic-session-result")


if __name__ == "__main__":
    unittest.main(verbosity=2)
