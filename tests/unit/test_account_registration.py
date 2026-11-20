"""Registration tests using fake sessions and a synthetic password hasher."""
import runpy
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert

ROOT = Path(__file__).resolve().parents[2]
module = runpy.run_path(str(ROOT / "database/repositories/account_registration.py"))
Registration = module["PendingAccountRegistration"]
ORG, USER = UUID(int=1), UUID(int=2)
GOOGLE = {
    "issuer": "https://accounts.google.com",
    "subject": "synthetic-subject",
    "email": "user@example.com",
    "full_name": "Example User",
}

def setup(replies):
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock()
    transaction.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value = transaction
    responses = []
    for value in replies:
        if isinstance(value, Exception):
            responses.append(value)
        else:
            response = MagicMock()
            response.mappings.return_value.first.return_value = value
            responses.append(response)
    session.execute = AsyncMock(side_effect=responses)
    factory = MagicMock(return_value=session)
    hasher = MagicMock(return_value="synthetic-hash-for-tests-only")
    service = Registration(factory, password_hasher=hasher)
    return service, session, transaction, factory, hasher

def parameters(session, index):
    statement = session.execute.await_args_list[index].args[0]
    return statement.compile(dialect=postgresql.dialect()).params

class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_password_account_starts_pending_without_roles(self):
        service, session, transaction, factory, hasher = setup([
            {"id": ORG}, None, None, None,
        ])
        result = await service.register_password(
            ORG, email="user@example.com", full_name=" Example User ",
            password="synthetic-password",
        )
        self.assertEqual(result["approval_status"], "pending")
        self.assertEqual(result["organization_id"], ORG)
        self.assertEqual(result["full_name"], "Example User")
        self.assertNotIn("password_hash", result)
        stored = parameters(session, 2)
        self.assertEqual(stored["password_hash"], "synthetic-hash-for-tests-only")
        self.assertEqual(stored["approval_status"], "pending")
        self.assertIsNone(stored["approval_decided_by"])
        self.assertIsNone(stored["approval_decided_at"])
        tables = [
            call.args[0].table.name for call in session.execute.await_args_list
            if isinstance(call.args[0], Insert)
        ]
        self.assertEqual(tables, ["users", "audit_logs"])
        hasher.assert_called_once_with("synthetic-password")

    async def test_google_account_created_with_mapping_and_no_password(self):
        service, session, transaction, factory, hasher = setup([
            {"id": ORG}, None, None, None, None, None,
        ])
        result = await service.google_account(ORG, verified_identity=GOOGLE)
        self.assertEqual(result["approval_status"], "pending")
        stored = parameters(session, 3)
        self.assertIsNone(stored["password_hash"])
        identity = parameters(session, 4)
        self.assertEqual(identity["subject"], GOOGLE["subject"])
        self.assertEqual(identity["organization_id"], ORG)
        self.assertEqual(identity["user_id"], result["account_id"])
        hasher.assert_not_called()

    async def test_existing_google_identity_reuses_account(self):
        for status in ("pending", "approved"):
            with self.subTest(status=status):
                existing = {
                    "id": USER, "organization_id": ORG,
                    "full_name": "Existing User",
                    "approval_status": status, "is_active": True,
                }
                service, session, transaction, factory, hasher = setup([
                    {"id": ORG}, existing,
                ])
                result = await service.google_account(ORG, verified_identity=GOOGLE)
                self.assertEqual(result["account_id"], USER)
                self.assertEqual(result["approval_status"], status)
                self.assertEqual(session.execute.await_count, 2)

    async def test_matching_email_does_not_link_google_automatically(self):
        service, session, transaction, factory, hasher = setup([
            {"id": ORG}, None, {"id": USER},
        ])
        with self.assertRaises(HTTPException) as caught:
            await service.google_account(ORG, verified_identity=GOOGLE)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertFalse(any(
            isinstance(call.args[0], Insert)
            for call in session.execute.await_args_list
        ))

    async def test_rejected_or_disabled_google_account_denied(self):
        for status, active in (("rejected", True), (None, True), ("approved", False)):
            with self.subTest(status=status, active=active):
                service, session, transaction, factory, hasher = setup([
                    {"id": ORG},
                    {"id": USER, "organization_id": ORG,
                     "full_name": "Existing User",
                     "approval_status": status, "is_active": active},
                ])
                with self.assertRaises(HTTPException) as caught:
                    await service.google_account(ORG, verified_identity=GOOGLE)
                self.assertEqual(caught.exception.status_code, 403)

    async def test_audit_failure_exits_transaction_with_error(self):
        service, session, transaction, factory, hasher = setup([
            {"id": ORG}, None, None, RuntimeError("synthetic audit failure"),
        ])
        with self.assertRaises(RuntimeError):
            await service.register_password(
                ORG, email="user@example.com", full_name="Example User",
                password="synthetic-password",
            )
        self.assertIs(transaction.__aexit__.await_args.args[0], RuntimeError)

    async def test_invalid_password_denied_before_hash_or_database(self):
        for password in ("short", "x" * 1025, "\ud800" * 12, None):
            with self.subTest(password_type=type(password).__name__):
                service, session, transaction, factory, hasher = setup([])
                with self.assertRaises(ValueError):
                    await service.register_password(
                        ORG, email="user@example.com", full_name="Example User",
                        password=password,
                    )
                hasher.assert_not_called()
                factory.assert_not_called()

    async def test_inactive_organization_denied(self):
        service, session, transaction, factory, hasher = setup([None])
        with self.assertRaises(HTTPException) as caught:
            await service.google_account(ORG, verified_identity=GOOGLE)
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(session.execute.await_count, 1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
