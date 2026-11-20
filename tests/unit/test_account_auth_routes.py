"""Standalone HTTP tests with mocked authentication and rate limiting."""
import runpy
import secrets
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
module = runpy.run_path(
    str(ROOT / "apps/api/app/api/v1/routes/account_auth.py")
)
ORG, USER, OTHER = [UUID(int=i) for i in (1, 2, 3)]
PASSWORD = "synthetic-password"
BODY = {"email": "user@example.com", "password": PASSWORD}

def build(*, limited=False):
    token = secrets.token_urlsafe(32)
    service = SimpleNamespace(
        register_password=AsyncMock(return_value={
            "account_id": USER, "organization_id": ORG,
            "full_name": "Example User", "approval_status": "pending",
            "password_hash": "must-not-be-returned",
        }),
        login_password=AsyncMock(return_value=token),
        logout=AsyncMock(return_value=True),
    )
    async def organization():
        return ORG
    async def authentication():
        return service
    async def rate_guard():
        if limited:
            raise HTTPException(429, "too many requests")
    app = FastAPI()
    app.include_router(module["create_account_auth_router"](
        get_organization=organization,
        get_service=authentication,
        rate_guard=rate_guard,
    ), prefix="/api/v1")
    return TestClient(app), service, token

class Tests(unittest.TestCase):
    def test_defaults_reject_unconfigured_requests(self):
        app = FastAPI()
        app.include_router(
            module["create_account_auth_router"](), prefix="/api/v1",
        )
        with TestClient(app) as client:
            response = client.post("/api/v1/auth/login", json=BODY)
        self.assertEqual(response.status_code, 503)

    def test_registration_returns_pending_without_credentials(self):
        client, service, token = build()
        with client:
            response = client.post("/api/v1/auth/register", json={
                **BODY, "full_name": "Example User",
            })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["approval_status"], "pending")
        self.assertNotIn("password_hash", response.json())
        self.assertEqual(response.headers["cache-control"], "no-store")
        service.register_password.assert_awaited_once_with(
            ORG, email=BODY["email"],
            full_name="Example User", password=PASSWORD,
        )

    def test_login_returns_bearer_session_with_no_cache(self):
        client, service, token = build()
        with client:
            response = client.post("/api/v1/auth/login", json=BODY)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "access_token": token, "token_type": "bearer",
        })
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn(PASSWORD, response.text)

    def test_extra_authority_fields_and_invalid_password_are_sanitized(self):
        cases = [
            {**BODY, "organization_id": str(OTHER)},
            {**BODY, "role": "admin"},
            {**BODY, "approval_status": "approved"},
            {**BODY, "email": "invalid-email"},
            {**BODY, "password": "PRIVATE_MARKER_" + "x" * 1024},
        ]
        for body in cases:
            with self.subTest(keys=list(body)):
                client, service, token = build()
                with client:
                    response = client.post("/api/v1/auth/login", json=body)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json(), {
                    "detail": "invalid authentication request",
                })
                self.assertNotIn("PRIVATE_MARKER", response.text)
                self.assertNotIn(PASSWORD, response.text)
                service.login_password.assert_not_awaited()

    def test_rate_limit_prevents_authentication(self):
        client, service, token = build(limited=True)
        with client:
            response = client.post("/api/v1/auth/login", json=BODY)
        self.assertEqual(response.status_code, 429)
        service.login_password.assert_not_awaited()

    def test_bad_credentials_preserve_401(self):
        client, service, token = build()
        service.login_password.side_effect = HTTPException(401, "invalid sign-in")
        with client:
            response = client.post("/api/v1/auth/login", json=BODY)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(PASSWORD, response.text)

    def test_foreign_registration_response_rejected(self):
        client, service, token = build()
        service.register_password.return_value = {
            "account_id": USER, "organization_id": OTHER,
            "full_name": "Example User", "approval_status": "pending",
        }
        with client:
            response = client.post("/api/v1/auth/register", json={
                **BODY, "full_name": "Example User",
            })
        self.assertEqual(response.status_code, 503)

    def test_logout_revokes_header_session(self):
        client, service, token = build()
        with client:
            response = client.post("/api/v1/auth/logout", headers={
                "Authorization": "Bearer " + token,
            })
            missing = client.post("/api/v1/auth/logout")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(missing.status_code, 401)
        service.logout.assert_awaited_once_with(token)

if __name__ == "__main__":
    unittest.main(verbosity=2)
