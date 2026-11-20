"""Fake-session tests only; no database or existing application imports."""

import hashlib
import runpy
import secrets
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

ROOT = Path(__file__).resolve().parents[2]
module = runpy.run_path(str(ROOT / "database/repositories/account_sessions.py"))
AccountSessions = module["AccountSessions"]
USER, ORG, SESSION = [UUID(int=i) for i in (1, 2, 3)]


def result(value):
    response = MagicMock()
    response.mappings.return_value.first.return_value = value
    response.mappings.return_value.all.return_value = value
    return response


def setup(replies):
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock()
    transaction.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value = transaction
    session.execute = AsyncMock(
        side_effect=[value if isinstance(value, Exception) else result(value) for value in replies]
    )
    factory = MagicMock(return_value=session)
    service = AccountSessions(
        factory,
        principal_factory=lambda **values: SimpleNamespace(**values),
    )
    return service, session, transaction, factory


def state(status="approved"):
    return {
        "user_id": USER,
        "organization_id": ORG,
        "approval_status": status,
    }


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_issue_stores_digest_and_audit_only(self):
        for method in ("password", "google"):
            with self.subTest(method=method):
                service, session, transaction, _factory = setup(
                    [
                        {"id": USER, "organization_id": ORG, "approval_status": "pending"},
                        None,
                        None,
                    ]
                )
                token = await service.issue_authenticated(USER, ORG, auth_method=method)
                self.assertEqual(len(token), 43)
                statement = session.execute.await_args_list[1].args[0]
                parameters = statement.compile(dialect=postgresql.dialect()).params
                self.assertEqual(
                    parameters["token_digest"],
                    hashlib.sha256(token.encode("ascii")).hexdigest(),
                )
                self.assertNotIn(token, parameters.values())
                self.assertEqual(parameters["auth_method"], method)
                self.assertEqual(session.execute.await_count, 3)
                self.assertIsNone(transaction.__aexit__.await_args.args[0])

    async def test_audit_failure_prevents_token_return(self):
        service, _session, transaction, _factory = setup(
            [
                {"id": USER, "organization_id": ORG, "approval_status": "approved"},
                None,
                RuntimeError("synthetic audit failure"),
            ]
        )
        with self.assertRaises(RuntimeError):
            await service.issue_authenticated(USER, ORG, auth_method="password")
        self.assertIs(transaction.__aexit__.await_args.args[0], RuntimeError)

    async def test_pending_session_has_no_roles(self):
        service, session, _transaction, _factory = setup([state("pending")])
        principal = await service.verify(secrets.token_urlsafe(32))
        self.assertEqual(principal.subject, str(USER))
        self.assertEqual(principal.tenant_id, str(ORG))
        self.assertEqual(principal.roles, frozenset())
        self.assertEqual(session.execute.await_count, 1)

    async def test_approved_session_reads_current_roles(self):
        service, _session, _transaction, _factory = setup(
            [
                state(),
                [{"name": "viewer"}],
            ]
        )
        principal = await service.verify(secrets.token_urlsafe(32))
        self.assertEqual(principal.roles, frozenset({"viewer"}))
        service, _session, _transaction, _factory = setup(
            [
                state(),
                [{"name": "unknown_privileged_role"}],
            ]
        )
        with self.assertRaises(HTTPException):
            await service.verify(secrets.token_urlsafe(32))

    async def test_invalid_tokens_rejected_without_session(self):
        for token in (None, "", "short", "!" * 43, "A" * 42 + "B"):
            with self.subTest(token_type=type(token).__name__):
                service, _session, _transaction, factory = setup([])
                with self.assertRaises(HTTPException):
                    await service.verify(token)
                factory.assert_not_called()

    async def test_missing_or_expired_session_denied_and_sql_filtered(self):
        service, session, _transaction, _factory = setup([None])
        with self.assertRaises(HTTPException) as caught:
            await service.verify(secrets.token_urlsafe(32))
        self.assertEqual(caught.exception.status_code, 401)
        statement = session.execute.await_args.args[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        for fragment in (
            "account_sessions.revoked_at IS NULL",
            "account_sessions.expires_at >",
            "account_sessions.issued_at <=",
            "users.is_active IS true",
            "organizations.is_active IS true",
            "account_sessions.organization_id = users.organization_id",
            "FOR SHARE",
        ):
            self.assertIn(fragment, sql)

    async def test_revoke_and_repeat_logout(self):
        token = secrets.token_urlsafe(32)
        service, session, _transaction, _factory = setup(
            [
                {"id": SESSION, "organization_id": ORG, "user_id": USER},
                None,
            ]
        )
        self.assertTrue(await service.revoke(token))
        self.assertEqual(session.execute.await_count, 2)
        service, session, _transaction, _factory = setup([None])
        self.assertFalse(await service.revoke(token))
        self.assertEqual(session.execute.await_count, 1)

    async def test_unavailable_account_cannot_receive_session(self):
        service, session, _transaction, _factory = setup([None])
        with self.assertRaises(HTTPException):
            await service.issue_authenticated(USER, ORG, auth_method="google")
        self.assertEqual(session.execute.await_count, 1)
        with self.assertRaises(ValueError):
            await service.issue_authenticated(USER, ORG, auth_method="public")


if __name__ == "__main__":
    unittest.main(verbosity=2)
