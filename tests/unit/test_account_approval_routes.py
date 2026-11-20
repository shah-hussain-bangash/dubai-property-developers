"""Standalone HTTP tests using synthetic identities and a fake service."""

import json
import runpy
import unittest
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

namespace = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "apps/api/app/api/v1/routes/accounts.py")
)
Actor = namespace["AccountActor"]
create_router = namespace["create_accounts_router"]
ORG, OWNER, USER, OTHER_ORG = [UUID(int=n) for n in (1, 2, 3, 4)]


class FakeService:
    def __init__(self):
        self.calls = []
        self.row_org = ORG

    def owner_subject(self, organization_id):
        return OWNER if organization_id == ORG else None

    def row(self, subject=USER, status="pending"):
        return {
            "account_id": subject,
            "organization_id": self.row_org,
            "full_name": "Synthetic User",
            "approval_status": status,
            "password_hash": "synthetic-sensitive-value",
        }

    async def list_pending(self, actor, *, limit):
        self.calls.append("list")
        return [self.row()]

    async def decide(self, actor, target_id, *, approve):
        self.calls.append(("decide", actor.user_id, target_id, approve))
        return self.row(target_id, "approved" if approve else "rejected")

    async def get_self(self, actor):
        self.calls.append("self")
        return self.row(actor.user_id)


class AccountRouteTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()

    def client(self, subject=OWNER, *, configured_service=True):
        async def actor():
            return Actor(subject, ORG)

        async def service():
            return self.service

        options = {"get_actor": actor}
        if configured_service:
            options["get_service"] = service
        app = FastAPI()
        app.include_router(create_router(**options), prefix="/api/v1")
        return TestClient(app)

    def decision_path(self, subject=USER):
        return f"/api/v1/accounts/{subject}/approval"

    def test_default_authentication_denies(self):
        app = FastAPI()
        app.include_router(create_router(), prefix="/api/v1")
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/v1/accounts/me").status_code, 401)

    def test_missing_service_denies(self):
        with self.client(configured_service=False) as client:
            self.assertEqual(client.get("/api/v1/accounts/me").status_code, 503)

    def test_non_owner_cannot_list_or_decide(self):
        with self.client(USER) as client:
            self.assertEqual(client.get("/api/v1/accounts/approvals/pending").status_code, 403)
            self.assertEqual(
                client.post(self.decision_path(), json={"approve": True}).status_code,
                403,
            )
        self.assertEqual(self.service.calls, [])

    def test_owner_can_list_pending_without_hash_leak(self):
        with self.client() as client:
            response = client.get("/api/v1/accounts/approvals/pending")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["approval_status"], "pending")
        self.assertNotIn("password_hash", response.text)

    def test_owner_can_approve_and_reject(self):
        with self.client() as client:
            for approve, expected in ((True, "approved"), (False, "rejected")):
                response = client.post(self.decision_path(), json={"approve": approve})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["approval_status"], expected)
                self.assertNotIn("password_hash", response.text)

    def test_self_approval_denied(self):
        with self.client() as client:
            response = client.post(self.decision_path(OWNER), json={"approve": True})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.service.calls, [])

    def test_client_cannot_supply_owner_role_or_status(self):
        with self.client() as client:
            for field in ("owner_user_id", "actor_user_id", "role", "approval_status"):
                response = client.post(self.decision_path(), json={"approve": True, field: "admin"})
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.service.calls, [])

    def test_decision_boolean_is_strict(self):
        with self.client() as client:
            for value in ("yes", "true", 1, None):
                response = client.post(self.decision_path(), json={"approve": value})
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.service.calls, [])

    def test_cross_organization_response_denied(self):
        self.service.row_org = OTHER_ORG
        with self.client() as client:
            response = client.get("/api/v1/accounts/approvals/pending")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("Synthetic User", response.text)

    def test_me_returns_only_authenticated_account(self):
        with self.client(USER) as client:
            response = client.get("/api/v1/accounts/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["account_id"], str(USER))
        self.assertNotIn("password_hash", response.text)

    def test_pending_list_limit_is_bounded(self):
        with self.client() as client:
            self.assertEqual(
                client.get("/api/v1/accounts/approvals/pending?limit=101").status_code,
                422,
            )
        self.assertEqual(self.service.calls, [])


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(AccountRouteTests)
    )
    print(
        json.dumps(
            {
                "tests_run": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
                "skipped": len(result.skipped),
                "successful": result.wasSuccessful(),
            }
        )
    )
    raise SystemExit(0 if result.wasSuccessful() else 1)
