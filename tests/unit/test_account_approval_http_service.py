"""HTTP routes plus transactional service, using fake SQL sessions only."""

import runpy
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.sql.dml import Insert

ROOT = Path(__file__).resolve().parents[2]
helpers = runpy.run_path(str(ROOT / "tests/unit/test_account_approval_service.py"))
routes = runpy.run_path(str(ROOT / "apps/api/app/api/v1/routes/accounts.py"))
ORG = helpers["ORG"]
OWNER = helpers["OWNER"]
USER = helpers["USER"]
row = helpers["row"]
setup_service = helpers["setup_service"]
AccountActor = routes["AccountActor"]


def client_for(replies, *, user=OWNER, raise_errors=True):
    service, session = setup_service(replies)

    async def get_actor():
        return AccountActor(user_id=user, organization_id=ORG)

    async def get_service():
        return service

    app = FastAPI()
    app.include_router(
        routes["create_accounts_router"](
            get_actor=get_actor,
            get_service=get_service,
        ),
        prefix="/api/v1",
    )
    client = TestClient(app, raise_server_exceptions=raise_errors)
    return client, session


class Tests(unittest.TestCase):
    def test_owner_can_list_pending_accounts(self):
        client, session = client_for(
            [
                {"id": ORG},
                {"id": OWNER},
                [row("pending")],
            ]
        )
        with client:
            response = client.get("/api/v1/accounts/approvals/pending?limit=10")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {
                    "account_id": str(USER),
                    "organization_id": str(ORG),
                    "full_name": "Example User",
                    "approval_status": "pending",
                }
            ],
        )
        self.assertIn("commit", session.events)

    def test_approve_and_reject_reach_service_and_audit(self):
        for approve, status in ((True, "approved"), (False, "rejected")):
            with self.subTest(status=status):
                client, session = client_for(
                    [
                        {"id": ORG},
                        {"id": OWNER},
                        row(status),
                        None,
                    ]
                )
                with client:
                    response = client.post(
                        f"/api/v1/accounts/{USER}/approval",
                        json={"approve": approve},
                    )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["approval_status"], status)
                self.assertEqual(response.json()["account_id"], str(USER))
                self.assertIsInstance(session.statements[-1], Insert)
                self.assertEqual(session.events, ["open", "begin", "commit", "close"])

    def test_ineligible_target_returns_409(self):
        client, session = client_for(
            [
                {"id": ORG},
                {"id": OWNER},
                None,
            ]
        )
        with client:
            response = client.post(
                f"/api/v1/accounts/{USER}/approval",
                json={"approve": True},
            )
        self.assertEqual(response.status_code, 409)
        self.assertIn("rollback", session.events)
        self.assertFalse(any(isinstance(statement, Insert) for statement in session.statements))

    def test_nonowner_and_self_approval_denied_before_database(self):
        for user, target in ((USER, OWNER), (OWNER, OWNER)):
            with self.subTest(user=user):
                client, session = client_for([], user=user)
                with client:
                    response = client.post(
                        f"/api/v1/accounts/{target}/approval",
                        json={"approve": True},
                    )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(session.events, [])

    def test_current_owner_and_organization_state_checked(self):
        for replies in ([None], [{"id": ORG}, None]):
            with self.subTest(replies=replies):
                client, session = client_for(replies)
                with client:
                    response = client.post(
                        f"/api/v1/accounts/{USER}/approval",
                        json={"approve": True},
                    )
                self.assertEqual(response.status_code, 403)
                self.assertIn("rollback", session.events)

    def test_audit_failure_does_not_return_success(self):
        client, session = client_for(
            [
                {"id": ORG},
                {"id": OWNER},
                row(),
                RuntimeError("synthetic audit failure"),
            ],
            raise_errors=False,
        )
        with client:
            response = client.post(
                f"/api/v1/accounts/{USER}/approval",
                json={"approve": True},
            )
        self.assertEqual(response.status_code, 500)
        self.assertIn("rollback", session.events)
        self.assertNotIn("commit", session.events)
        self.assertNotIn("synthetic audit failure", response.text)

    def test_me_returns_pending_status_for_own_account(self):
        client, _session = client_for(
            [
                {"id": ORG},
                row("pending"),
            ],
            user=USER,
        )
        with client:
            response = client.get("/api/v1/accounts/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["account_id"], str(USER))
        self.assertEqual(response.json()["approval_status"], "pending")
        self.assertNotIn("password_hash", response.json())

    def test_invalid_body_rejected_before_service_execution(self):
        bodies = [
            {"approve": "yes"},
            {"approve": True, "owner_id": str(OWNER)},
            {"approve": True, "organization_id": str(ORG)},
        ]
        for body in bodies:
            with self.subTest(body=body):
                client, session = client_for([])
                with client:
                    response = client.post(
                        f"/api/v1/accounts/{USER}/approval",
                        json=body,
                    )
                self.assertEqual(response.status_code, 422)
                self.assertEqual(session.events, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
