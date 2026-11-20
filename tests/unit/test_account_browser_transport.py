"""Standalone browser transport contracts; all session services are fake."""

import runpy
import secrets
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
factory = runpy.run_path(str(ROOT / "apps/api/app/dependencies/account_browser.py"))[
    "create_browser_session_transport"
]
ORG, USER = UUID(int=1), UUID(int=2)
ORIGIN = "https://app.example.com"
SECRET = b"synthetic-csrf-secret-for-tests-only-532"
COOKIE = "__Host-account_session"


def build(*, origin=ORIGIN, allow_local_http=False, limited=False, **overrides):
    token = secrets.token_urlsafe(32)
    principal = SimpleNamespace(subject=str(USER), tenant_id=str(ORG), roles=frozenset())
    sessions = SimpleNamespace(verify=AsyncMock(return_value=principal), revoke=AsyncMock())
    changes = []

    async def organization():
        return ORG

    async def get_sessions():
        return sessions

    async def guard():
        if limited:
            raise HTTPException(429, "rate limited")

    options = dict(
        trusted_origin=origin,
        csrf_secret=SECRET,
        actor_factory=lambda **fields: SimpleNamespace(**fields),
        get_organization=organization,
        get_sessions=get_sessions,
        rate_guard=guard,
        allow_local_http=allow_local_http,
    )
    options.update(overrides)
    transport = factory(**options)
    app = FastAPI()
    app.include_router(transport["router"], prefix="/api/v1")

    @app.get("/identity")
    async def identity(actor=Depends(transport["get_actor"])):
        return {"subject": str(actor.user_id), "tenant": str(actor.organization_id)}

    @app.post("/change")
    async def change(verified=Depends(transport["principal_dependency"])):
        changes.append(verified.subject)
        return {"ok": True}

    client = TestClient(app, base_url=origin)
    cookie = "account_session_local" if origin.startswith("http:") else COOKIE
    client.cookies.set(cookie, token)
    return client, sessions, token, principal, changes


def csrf_headers(client):
    response = client.get("/api/v1/auth/browser/csrf")
    assert response.status_code == 200
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


class Tests(unittest.TestCase):
    def test_google_callback_cookie_through_csrf_and_revocation(self):
        google = runpy.run_path(str(ROOT / "tests/unit/test_account_google_routes.py"))
        client, _provider, _authentication, _store, _context, token = google["build"]()
        revoked = set()

        async def verify(supplied):
            if supplied != token or supplied in revoked:
                raise HTTPException(401, "invalid session")
            return SimpleNamespace(subject=str(USER), tenant_id=str(ORG), roles=frozenset())

        async def revoke(supplied):
            revoked.add(supplied)
            return True

        async def organization():
            return ORG

        async def sessions():
            return SimpleNamespace(verify=verify, revoke=revoke)

        async def guard():
            return None

        transport = factory(
            trusted_origin=ORIGIN,
            csrf_secret=SECRET,
            actor_factory=lambda **fields: fields,
            get_organization=organization,
            get_sessions=sessions,
            rate_guard=guard,
        )
        client.app.include_router(transport["router"], prefix="/api/v1")
        with client:
            client.get("/api/v1/auth/google/start", follow_redirects=False)
            callback = client.get(google["CALLBACK"], follow_redirects=False)
            self.assertEqual(callback.status_code, 303)
            self.assertEqual(client.cookies.get(COOKIE), token)
            headers = csrf_headers(client)
            logout = client.post("/api/v1/auth/browser/logout", headers=headers)
            stolen = client.get(
                "/api/v1/auth/browser/csrf", headers={"Cookie": COOKIE + "=" + token}
            )
        self.assertEqual(logout.status_code, 204)
        self.assertIn(token, revoked)
        self.assertEqual(stolen.status_code, 401)

    def test_csrf_is_bound_to_organization_and_server_secret(self):
        client, _sessions, token, _principal, _changes = build()
        with client:
            headers = csrf_headers(client)
        for override in (
            {"csrf_secret": b"another-synthetic-secret-of-at-least-32-bytes"},
            {"get_organization": self.other_organization},
        ):
            with self.subTest(override=override):
                other, sessions, _token, _principal, changes = build(**override)
                other.cookies.set(COOKIE, token)
                with other:
                    response = other.post("/change", headers=headers)
                self.assertEqual(response.status_code, 403)
                sessions.verify.assert_not_awaited()
                self.assertEqual(changes, [])

    @staticmethod
    async def other_organization():
        return UUID(int=99)

    def test_cookie_authentication_produces_internal_actor(self):
        client, sessions, token, _principal, _changes = build()
        with client:
            response = client.get("/identity", headers={"X-User-Id": str(UUID(int=99))})
        self.assertEqual(response.json(), {"subject": str(USER), "tenant": str(ORG)})
        sessions.verify.assert_awaited_once_with(token)

    def test_csrf_token_is_private_and_does_not_reveal_session(self):
        client, _sessions, token, _principal, _changes = build()
        with client:
            response = client.get("/api/v1/auth/browser/csrf")
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.json()["csrf_token"], r"^[0-9a-f]{64}$")
        self.assertNotIn(token, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")

    def test_mutation_requires_matching_origin_and_csrf(self):
        client, _sessions, _token, _principal, changes = build()
        with client:
            response = client.post("/change", headers=csrf_headers(client))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(changes, [str(USER)])

    def test_missing_wrong_duplicate_and_foreign_csrf_denied_before_verify(self):
        for case in (
            "missing",
            "wrong",
            "foreign_origin",
            "null_origin",
            "missing_origin",
            "duplicate_token",
            "duplicate_origin",
        ):
            with self.subTest(case=case):
                client, sessions, _token, _principal, changes = build()
                with client:
                    headers = csrf_headers(client)
                    if case == "missing":
                        del headers["X-CSRF-Token"]
                    elif case == "wrong":
                        headers["X-CSRF-Token"] = "0" * 64
                    elif case == "foreign_origin":
                        headers["Origin"] = "https://evil.example.com"
                    elif case == "null_origin":
                        headers["Origin"] = "null"
                    elif case == "missing_origin":
                        del headers["Origin"]
                    else:
                        name = "Origin" if case == "duplicate_origin" else "X-CSRF-Token"
                        headers = [*headers.items(), (name, headers[name])]
                    sessions.verify.reset_mock()
                    response = client.post("/change", headers=headers)
                self.assertEqual(response.status_code, 403)
                sessions.verify.assert_not_awaited()
                self.assertEqual(changes, [])

    def test_csrf_token_cannot_move_to_another_session(self):
        client, sessions, _token, _principal, changes = build()
        with client:
            headers = csrf_headers(client)
            client.cookies.set(COOKIE, secrets.token_urlsafe(32))
            sessions.verify.reset_mock()
            response = client.post("/change", headers=headers)
        self.assertEqual(response.status_code, 403)
        sessions.verify.assert_not_awaited()
        self.assertEqual(changes, [])

    def test_bad_missing_noncanonical_or_duplicate_session_rejected(self):
        for value in (
            "",
            COOKIE + "=short",
            COOKIE + "=" + "_" * 43,
            COOKIE
            + "="
            + secrets.token_urlsafe(32)
            + "; "
            + COOKIE
            + "="
            + secrets.token_urlsafe(32),
        ):
            with self.subTest(cookie=value):
                client, sessions, _token, _principal, _changes = build()
                with client:
                    response = client.get("/identity", headers={"Cookie": value})
                self.assertEqual(response.status_code, 401)
                sessions.verify.assert_not_awaited()

    def test_cookie_and_authorization_header_are_ambiguous(self):
        client, sessions, _token, _principal, _changes = build()
        with client:
            response = client.get("/identity", headers={"Authorization": "Bearer other"})
        self.assertEqual(response.status_code, 400)
        sessions.verify.assert_not_awaited()

    def test_request_origin_must_match_trusted_configuration(self):
        client, sessions, _token, _principal, _changes = build()
        with client:
            for origin in ("http://app.example.com", "https://other.example.com"):
                self.assertEqual(client.get(origin + "/identity").status_code, 400)
        sessions.verify.assert_not_awaited()

    def test_untrusted_or_wrong_tenant_identity_is_rejected(self):
        for fields in (
            {"subject": "external-google-id"},
            {"subject": str(UUID(int=0))},
            {"tenant_id": str(UUID(int=99))},
            {"tenant_id": None},
        ):
            with self.subTest(fields=fields):
                client, _sessions, _token, principal, _changes = build()
                for name, value in fields.items():
                    setattr(principal, name, value)
                with client:
                    self.assertEqual(client.get("/identity").status_code, 401)

    def test_verification_errors_are_sanitized(self):
        for error, status in (
            (HTTPException(401, "private diagnostic"), 401),
            (RuntimeError("private diagnostic"), 503),
        ):
            with self.subTest(error=repr(error)):
                client, sessions, _token, _principal, _changes = build()
                sessions.verify.side_effect = error
                with client:
                    response = client.get("/identity")
                self.assertEqual(response.status_code, status)
                self.assertNotIn("private diagnostic", response.text)

    def test_logout_revokes_and_clears_both_cookies(self):
        client, sessions, token, _principal, _changes = build()
        with client:
            response = client.post("/api/v1/auth/browser/logout", headers=csrf_headers(client))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        sessions.revoke.assert_awaited_once_with(token)
        for cookie in response.headers.get_list("set-cookie"):
            for flag in ("Max-Age=0", "Secure", "HttpOnly", "SameSite=lax", "Path=/"):
                self.assertIn(flag, cookie)
        self.assertEqual(len(response.headers.get_list("set-cookie")), 2)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_logout_requires_csrf_and_never_revokes_on_rejection(self):
        client, sessions, _token, _principal, _changes = build()
        with client:
            response = client.post("/api/v1/auth/browser/logout")
        self.assertEqual(response.status_code, 403)
        sessions.revoke.assert_not_awaited()

    def test_revocation_failure_does_not_claim_logout(self):
        client, sessions, _token, _principal, _changes = build()
        sessions.revoke.side_effect = RuntimeError("private diagnostic")
        with client:
            response = client.post("/api/v1/auth/browser/logout", headers=csrf_headers(client))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private diagnostic", response.text)
        self.assertNotIn("set-cookie", response.headers)

    def test_rate_limit_blocks_session_verification(self):
        client, sessions, _token, _principal, _changes = build(limited=True)
        with client:
            self.assertEqual(client.get("/identity").status_code, 429)
        sessions.verify.assert_not_awaited()

    def test_defaults_fail_closed(self):
        transport = factory(
            trusted_origin=ORIGIN, csrf_secret=SECRET, actor_factory=lambda **fields: fields
        )
        app = FastAPI()
        app.include_router(transport["router"])
        with TestClient(app, base_url=ORIGIN) as client:
            self.assertEqual(client.get("/auth/browser/csrf").status_code, 503)

    def test_local_http_requires_opt_in_and_separate_cookie(self):
        client, _sessions, _token, _principal, _changes = build(
            origin="http://localhost:8000", allow_local_http=True
        )
        with client:
            response = client.get("/api/v1/auth/browser/csrf")
            headers = {
                "Origin": "http://localhost:8000",
                "X-CSRF-Token": response.json()["csrf_token"],
            }
            logout = client.post("/api/v1/auth/browser/logout", headers=headers)
        self.assertEqual(logout.status_code, 204)
        self.assertTrue(
            logout.headers.get_list("set-cookie")[0].startswith("account_session_local=")
        )
        self.assertNotIn("Secure", logout.headers.get_list("set-cookie")[0])

    def test_invalid_configuration_rejected(self):
        for override in (
            {"csrf_secret": b"short"},
            {"allow_local_http": "true"},
            {"actor_factory": None},
            {"trusted_origin": "http://app.example.com"},
            {"trusted_origin": "https://app.example.com/path"},
            {"trusted_origin": "https://user@app.example.com"},
            {"trusted_origin": "https://app.example.com:bad"},
        ):
            with self.subTest(override=override), self.assertRaises(ValueError):
                build(**override)


if __name__ == "__main__":
    unittest.main(verbosity=2)
