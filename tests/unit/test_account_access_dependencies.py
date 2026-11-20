"""Dependency tests with synthetic principals; no real tokens or database."""

import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
adapter = runpy.run_path(str(ROOT / "apps/api/app/dependencies/account_access.py"))
routes = runpy.run_path(str(ROOT / "apps/api/app/api/v1/routes/accounts.py"))
USER, ORG = UUID(int=1), UUID(int=2)


class FakeService:
    def __init__(self, status):
        self.status = status
        self.calls = []

    def owner_subject(self, organization_id):
        return None

    async def list_pending(self, actor, *, limit):
        return []

    async def decide(self, actor, target_id, *, approve):
        raise AssertionError("unexpected decision")

    async def get_self(self, actor):
        return {}

    async def require_dashboard_access(self, actor):
        self.calls.append(actor)
        if self.status != "approved":
            raise HTTPException(403, "approved account required")
        return {"account_id": str(actor.user_id)}


def build(
    *, mode="token", verifier=True, subject=None, tenant=None, service=None, principal_error=False
):
    calls = []

    async def principal_dependency(request):
        calls.append("principal")
        if principal_error:
            raise HTTPException(401, "invalid token")
        return SimpleNamespace(
            subject=str(USER) if subject is None else subject,
            tenant_id=str(ORG) if tenant is None else tenant,
        )

    dependencies = adapter["build_account_dependencies"](
        principal_dependency=principal_dependency,
        actor_factory=routes["AccountActor"],
    )
    app = FastAPI()
    app.state.settings = SimpleNamespace(auth_mode=mode)
    if verifier:
        app.state.token_verifier = SimpleNamespace(verify=lambda token: None)
    if service is not None:
        app.state.account_service = service

    @app.get("/identity")
    async def identity(actor=Depends(dependencies["get_actor"])):
        return {"user": str(actor.user_id), "organization": str(actor.organization_id)}

    @app.get("/protected-test")
    async def protected(result=Depends(dependencies["require_dashboard_access"])):
        return result

    return TestClient(app), calls


AUTH = {"Authorization": "Bearer synthetic-test-token"}


class Tests(unittest.TestCase):
    def test_verified_identity_converted_to_account_actor(self):
        client, calls = build()
        with client:
            response = client.get("/identity", headers=AUTH)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "user": str(USER),
                "organization": str(ORG),
            },
        )
        self.assertEqual(calls, ["principal"])

    def test_dev_mode_rejected_before_principal(self):
        client, calls = build(mode="dev")
        with client:
            response = client.get("/identity", headers=AUTH)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(calls, [])

    def test_missing_verifier_rejected_before_principal(self):
        client, calls = build(verifier=False)
        with client:
            response = client.get("/identity", headers=AUTH)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(calls, [])

    def test_missing_or_malformed_bearer_rejected(self):
        for headers in (
            {},
            {"Authorization": "Basic abc"},
            {"Authorization": "Bearer"},
            {"Authorization": "Bearer a b"},
        ):
            with self.subTest(headers=headers):
                client, calls = build()
                with client:
                    response = client.get("/identity", headers=headers)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(calls, [])

    def test_invalid_internal_identity_rejected(self):
        for values in (
            {"subject": "dev-user"},
            {"tenant": "external-tenant"},
            {"subject": str(UUID(int=0))},
            {"subject": 123},
        ):
            with self.subTest(values=values):
                client, _calls = build(**values)
                with client:
                    response = client.get("/identity", headers=AUTH)
                self.assertEqual(response.status_code, 401)

    def test_request_identity_headers_do_not_override_principal(self):
        client, _calls = build()
        with client:
            response = client.get(
                "/identity",
                headers={
                    **AUTH,
                    "X-User-Id": str(UUID(int=99)),
                    "X-Tenant-Id": str(UUID(int=98)),
                    "X-Dev-Roles": "admin",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"], str(USER))
        self.assertEqual(response.json()["organization"], str(ORG))

    def test_principal_rejection_preserved(self):
        client, _calls = build(principal_error=True)
        with client:
            response = client.get("/identity", headers=AUTH)
        self.assertEqual(response.status_code, 401)

    def test_missing_service_returns_503(self):
        client, _calls = build()
        with client:
            response = client.get("/protected-test", headers=AUTH)
        self.assertEqual(response.status_code, 503)

    def test_dashboard_checks_current_approval(self):
        for status in (None, "pending", "rejected", "approved"):
            with self.subTest(status=status):
                service = FakeService(status)
                client, _calls = build(service=service)
                with client:
                    response = client.get("/protected-test", headers=AUTH)
                self.assertEqual(response.status_code, 200 if status == "approved" else 403)
                self.assertEqual(len(service.calls), 1)
                self.assertEqual(service.calls[0].user_id, USER)
                self.assertEqual(service.calls[0].organization_id, ORG)


if __name__ == "__main__":
    unittest.main(verbosity=2)
