"""Isolated service tests: fake sessions, no database or project imports."""
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert, Update

ROOT = Path(__file__).resolve().parents[2]
namespace = runpy.run_path(
    str(ROOT / "database/repositories/account_approval_service.py")
)
Service = namespace["TransactionalAccountService"]
ORG, OWNER, USER, OTHER = [UUID(int=i) for i in range(1, 5)]

def actor(user=OWNER):
    return SimpleNamespace(user_id=user, organization_id=ORG)

def row(status="approved"):
    return {
        "id": USER,
        "organization_id": ORG,
        "full_name": "Example User",
        "approval_status": status,
    }

class Result:
    def __init__(self, value):
        self.value = value
    def mappings(self):
        return self
    def first(self):
        return self.value
    def all(self):
        return self.value

class Transaction:
    def __init__(self, session):
        self.session = session
    async def __aenter__(self):
        self.session.events.append("begin")
    async def __aexit__(self, kind, error, traceback):
        self.session.events.append("rollback" if kind else "commit")
        return False

class Session:
    def __init__(self, replies):
        self.replies = list(replies)
        self.statements = []
        self.events = []
    async def __aenter__(self):
        self.events.append("open")
        return self
    async def __aexit__(self, kind, error, traceback):
        self.events.append("close")
        return False
    def begin(self):
        return Transaction(self)
    async def execute(self, statement):
        self.statements.append(statement)
        if not self.replies:
            raise AssertionError("unexpected SQL execution")
        value = self.replies.pop(0)
        if isinstance(value, Exception):
            raise value
        return Result(value)

def setup_service(replies):
    session = Session(replies)
    service = Service(lambda: session, owners={ORG: OWNER})
    return service, session

def compiled(statement):
    return statement.compile(dialect=postgresql.dialect())

class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_decision_and_audit_share_transaction(self):
        for approve, status in ((True, "approved"), (False, "rejected")):
            with self.subTest(status=status):
                service, session = setup_service([
                    {"id": ORG}, {"id": OWNER}, row(status), None,
                ])
                result = await service.decide(actor(), USER, approve=approve)
                self.assertEqual(result["approval_status"], status)
                self.assertEqual(
                    session.events, ["open", "begin", "commit", "close"]
                )
                self.assertEqual(len(session.statements), 4)
                self.assertIsInstance(session.statements[2], Update)
                self.assertIsInstance(session.statements[3], Insert)
                parameters = compiled(session.statements[3]).params
                self.assertEqual(parameters["actor"], str(OWNER))
                self.assertEqual(parameters["organization_id"], ORG)
                self.assertEqual(parameters["resource_id"], str(USER))
                self.assertEqual(parameters["outcome"], status)

    async def test_audit_failure_exits_with_rollback(self):
        service, session = setup_service([
            {"id": ORG}, {"id": OWNER}, row(), RuntimeError("audit unavailable"),
        ])
        with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
            await service.decide(actor(), USER, approve=True)
        self.assertEqual(
            session.events, ["open", "begin", "rollback", "close"]
        )

    async def test_no_eligible_target_returns_conflict_without_audit(self):
        service, session = setup_service([{"id": ORG}, {"id": OWNER}, None])
        with self.assertRaises(HTTPException) as caught:
            await service.decide(actor(), USER, approve=True)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(len(session.statements), 3)
        self.assertIn("rollback", session.events)

    async def test_inactive_organization_or_owner_denied(self):
        for replies in ([None], [{"id": ORG}, None]):
            with self.subTest(replies=replies):
                service, session = setup_service(replies)
                with self.assertRaises(HTTPException) as caught:
                    await service.decide(actor(), USER, approve=True)
                self.assertEqual(caught.exception.status_code, 403)
                self.assertFalse(any(
                    isinstance(stmt, (Insert, Update))
                    for stmt in session.statements
                ))

    async def test_invalid_decisions_rejected_before_session(self):
        cases = [
            (actor(USER), OTHER, True, HTTPException),
            (actor(), OWNER, True, HTTPException),
            (actor(), USER, "yes", ValueError),
            (actor(), "invalid", True, ValueError),
        ]
        for who, target, approve, error in cases:
            with self.subTest(target=target, approve=approve):
                service, session = setup_service([])
                with self.assertRaises(error):
                    await service.decide(who, target, approve=approve)
                self.assertEqual(session.events, [])

    async def test_postgresql_lock_and_update_sql(self):
        service, session = setup_service([
            {"id": ORG}, {"id": OWNER}, row(), None,
        ])
        await service.decide(actor(), USER, approve=True)
        for statement in session.statements[:2]:
            self.assertIn("FOR SHARE", str(compiled(statement)))
        update = compiled(session.statements[2])
        sql = str(update)
        self.assertIn("users.organization_id =", sql)
        self.assertIn("users.is_active IS true", sql)
        self.assertIn("users.approval_status =", sql)
        self.assertIn("RETURNING", sql)
        self.assertIn("pending", update.params.values())
        self.assertIn(ORG, update.params.values())
        self.assertIn(USER, update.params.values())
        self.assertNotIn("password_hash", sql)

    async def test_pending_listing_and_bounds(self):
        service, session = setup_service([
            {"id": ORG}, {"id": OWNER}, [row("pending")],
        ])
        result = await service.list_pending(actor(), limit=10)
        self.assertEqual(result[0]["approval_status"], "pending")
        self.assertEqual(len(result), 1)
        self.assertIn(10, compiled(session.statements[-1]).params.values())
        for limit in (0, 101, True):
            service, session = setup_service([])
            with self.assertRaises(ValueError):
                await service.list_pending(actor(), limit=limit)
            self.assertEqual(session.events, [])

    async def test_self_status_and_dashboard_gate(self):
        for status in (None, "pending", "rejected", "approved"):
            with self.subTest(status=status):
                service, session = setup_service([{"id": ORG}, row(status)])
                if status == "approved":
                    result = await service.require_dashboard_access(actor(USER))
                    self.assertEqual(result["account_id"], USER)
                else:
                    with self.assertRaises(HTTPException) as caught:
                        await service.require_dashboard_access(actor(USER))
                    self.assertEqual(caught.exception.status_code, 403)
                parameters = compiled(session.statements[-1]).params
                self.assertIn(USER, parameters.values())
                self.assertIn(ORG, parameters.values())

    async def test_missing_self_denied(self):
        service, session = setup_service([{"id": ORG}, None])
        with self.assertRaises(HTTPException) as caught:
            await service.get_self(actor(USER))
        self.assertEqual(caught.exception.status_code, 403)

    async def test_owner_configuration_copied(self):
        owners = {ORG: OWNER}
        service = Service(lambda: None, owners=owners)
        owners[ORG] = OTHER
        self.assertEqual(service.owner_subject(ORG), OWNER)
        self.assertIsNone(service.owner_subject(OTHER))

if __name__ == "__main__":
    unittest.main(verbosity=2)
