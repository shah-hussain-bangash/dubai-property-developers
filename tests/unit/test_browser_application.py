"""Opt-in application composition with fake Google, session and account services."""

import runpy
import secrets
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
install = runpy.run_path(str(ROOT / "apps/api/app/browser_application.py"))["install_browser_auth"]
ORG, OWNER, TARGET = UUID(int=1), UUID(int=2), UUID(int=3)
ORIGIN = "https://app.example.com"
STATE = "synthetic_google_state_step533"


def setup():
    app = FastAPI()
    token = secrets.token_urlsafe(32)
    principal = SimpleNamespace(subject=str(OWNER), tenant_id=str(ORG))
    sessions = SimpleNamespace(verify=AsyncMock(return_value=principal), revoke=AsyncMock())
    records = {}

    async def reserve(state, organization, binding):
        records[state] = (organization, binding)

    async def consume(state, organization, binding):
        if records.get(state) == (organization, binding):
            del records[state]
            return True
        return False

    async def start(request):
        request.session["synthetic_oauth_state"] = STATE
        return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?state=" + STATE)

    async def organization():
        return ORG

    async def guard():
        return None

    def row(user=OWNER, status="approved"):
        return {
            "account_id": user,
            "organization_id": ORG,
            "full_name": "Synthetic User",
            "approval_status": status,
        }

    accounts = SimpleNamespace(
        owner_subject=lambda organization: OWNER,
        get_self=AsyncMock(return_value=row()),
        list_pending=AsyncMock(return_value=[row(TARGET, "pending")]),
        decide=AsyncMock(return_value=row(TARGET)),
        require_dashboard_access=AsyncMock(),
    )
    options = dict(
        enabled=True,
        trusted_origin=ORIGIN,
        csrf_secret=b"synthetic-csrf-secret-at-least-32-bytes",
        oauth_session_secret="synthetic-oauth-secret-at-least-32-bytes",
        organization_dependency=organization,
        provider=SimpleNamespace(start=start),
        authentication=SimpleNamespace(login_google=AsyncMock(return_value=token)),
        sessions=sessions,
        flow_store=SimpleNamespace(reserve=reserve, consume=consume),
        account_service=accounts,
        rate_guard=guard,
    )
    return app, options, token, principal, accounts


class Tests(unittest.TestCase):
    def test_included_router_conflict_is_rejected(self):
        app, options, _token, _principal, _accounts = setup()
        existing = APIRouter(prefix="/api/v1")

        @existing.get("/accounts/me")
        async def endpoint():
            return {}

        app.include_router(existing)
        with self.assertRaises(ValueError):
            install(app, **options)
        self.assertEqual(app.user_middleware, [])

    def test_revoked_session_cannot_read_account(self):
        app, options, token, _principal, accounts = setup()
        options["sessions"].verify.side_effect = HTTPException(401, "revoked")
        install(app, **options)
        with TestClient(app, base_url=ORIGIN) as client:
            client.cookies.set("__Host-account_session", token)
            response = client.get("/api/v1/accounts/me")
        self.assertEqual(response.status_code, 401)
        accounts.get_self.assert_not_awaited()

    def test_disabled_by_default_has_no_routes_or_middleware(self):
        app = FastAPI()
        before = list(app.routes)
        self.assertFalse(install(app))
        self.assertEqual(app.routes, before)
        self.assertEqual(app.user_middleware, [])

    def test_incomplete_configuration_does_not_mutate_application(self):
        for name in (
            "sessions",
            "provider",
            "account_service",
            "rate_guard",
            "organization_dependency",
        ):
            with self.subTest(name=name):
                app, options, _token, _principal, _accounts = setup()
                options[name] = None
                before = list(app.routes)
                with self.assertRaises(ValueError):
                    install(app, **options)
                self.assertEqual(app.routes, before)
                self.assertEqual(app.user_middleware, [])

    def test_unsafe_origin_and_secrets_rejected(self):
        for changes in (
            {"trusted_origin": "https://app.example.com/path"},
            {"oauth_session_secret": "short"},
            {"csrf_secret": b"synthetic-oauth-secret-at-least-32-bytes"},
            {"enabled": "true"},
        ):
            with self.subTest(changes=changes):
                app, options, _token, _principal, _accounts = setup()
                options.update(changes)
                with self.assertRaises(ValueError):
                    install(app, **options)
                self.assertEqual(app.user_middleware, [])

    def test_cookie_signin_account_read_and_owner_decision_are_connected(self):
        app, options, token, _principal, accounts = setup()
        self.assertTrue(install(app, **options))
        with TestClient(app, base_url=ORIGIN) as client:
            start = client.get("/api/v1/auth/google/start", follow_redirects=False)
            self.assertEqual(start.status_code, 307)
            cookies = start.headers.get_list("set-cookie")
            self.assertTrue(any(cookie.startswith("__Host-account_oauth=") for cookie in cookies))
            callback = client.get(
                f"/api/v1/auth/google/callback?state={STATE}&code=synthetic", follow_redirects=False
            )
            self.assertEqual(callback.status_code, 303)
            self.assertEqual(client.cookies.get("__Host-account_session"), token)
            me = client.get("/api/v1/accounts/me")
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.headers["cache-control"], "no-store")
            self.assertEqual(client.get("/api/v1/accounts/approvals/pending").status_code, 200)
            csrf = client.get("/api/v1/auth/browser/csrf").json()["csrf_token"]
            decision = client.post(
                f"/api/v1/accounts/{TARGET}/approval",
                json={"approve": True},
                headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
            )
            self.assertEqual(decision.status_code, 200)
        accounts.decide.assert_awaited_once()

    def test_missing_csrf_cannot_make_owner_decision(self):
        app, options, token, _principal, accounts = setup()
        install(app, **options)
        with TestClient(app, base_url=ORIGIN) as client:
            client.cookies.set("__Host-account_session", token)
            response = client.post(f"/api/v1/accounts/{TARGET}/approval", json={"approve": True})
        self.assertEqual(response.status_code, 403)
        accounts.decide.assert_not_awaited()

    def test_nonowner_cannot_list_or_decide(self):
        app, options, token, principal, accounts = setup()
        principal.subject = str(TARGET)
        install(app, **options)
        with TestClient(app, base_url=ORIGIN) as client:
            client.cookies.set("__Host-account_session", token)
            csrf = client.get("/api/v1/auth/browser/csrf").json()["csrf_token"]
            self.assertEqual(client.get("/api/v1/accounts/approvals/pending").status_code, 403)
            response = client.post(
                f"/api/v1/accounts/{OWNER}/approval",
                json={"approve": True},
                headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 403)
        accounts.decide.assert_not_awaited()
        accounts.list_pending.assert_not_awaited()

    def test_rate_guard_protects_accounts_and_google_routes(self):
        app, options, token, _principal, accounts = setup()

        async def deny():
            raise HTTPException(429, "rate limited")

        options["rate_guard"] = deny
        install(app, **options)
        with TestClient(app, base_url=ORIGIN) as client:
            client.cookies.set("__Host-account_session", token)
            self.assertEqual(client.get("/api/v1/accounts/me").status_code, 429)
            self.assertEqual(client.get("/api/v1/auth/google/start").status_code, 429)
        accounts.get_self.assert_not_awaited()

    def test_route_conflict_rejected_before_middleware_mutation(self):
        app, options, _token, _principal, _accounts = setup()

        @app.get("/api/v1/accounts/me")
        async def existing():
            return {}

        with self.assertRaises(ValueError):
            install(app, **options)
        self.assertEqual(app.user_middleware, [])

    def test_existing_session_middleware_rejected(self):
        app, options, _token, _principal, _accounts = setup()
        app.add_middleware(SessionMiddleware, secret_key="synthetic-existing-session-secret")
        with self.assertRaises(ValueError):
            install(app, **options)

    def test_double_installation_rejected(self):
        app, options, _token, _principal, _accounts = setup()
        install(app, **options)
        with self.assertRaises(ValueError):
            install(app, **options)

    def test_installation_after_startup_rejected(self):
        app, options, _token, _principal, _accounts = setup()
        with TestClient(app), self.assertRaises(ValueError):
            install(app, **options)


if __name__ == "__main__":
    unittest.main(verbosity=2)
