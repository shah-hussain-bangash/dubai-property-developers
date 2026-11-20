"""Standalone browser-route contracts; Google and flow storage are fake."""

import runpy
import secrets
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

ROOT = Path(__file__).resolve().parents[2]
module = runpy.run_path(str(ROOT / "apps/api/app/api/v1/routes/account_google.py"))
ORG, OTHER = UUID(int=1), UUID(int=2)
STATE = "synthetic_google_state_1234567890"
CALLBACK = f"/api/v1/auth/google/callback?state={STATE}&code=synthetic-code"
FLOW_COOKIE = "__Host-account_google_flow"
SESSION_COOKIE = "__Host-account_session"


class FakeStore:
    def __init__(self):
        self.records = {}

    async def reserve(self, state, organization, binding):
        if state in self.records:
            raise ValueError("collision")
        self.records[state] = (organization, binding)

    async def consume(self, state, organization, binding):
        if self.records.get(state) == (organization, binding):
            del self.records[state]
            return True
        return False


def build(
    *, allow_local_http=False, with_session=True, limited=False, base_url="https://app.example.com"
):
    context = SimpleNamespace(organization=ORG)
    provider = SimpleNamespace(
        start=AsyncMock(
            return_value=RedirectResponse(
                "https://accounts.google.com/o/oauth2/v2/auth?state=" + STATE,
                status_code=302,
            )
        )
    )
    token = secrets.token_urlsafe(32)
    authentication = SimpleNamespace(login_google=AsyncMock(return_value=token))
    store = FakeStore()

    async def organization():
        return context.organization

    async def get_provider():
        return provider

    async def get_authentication():
        return authentication

    async def get_store():
        return store

    async def rate_guard():
        if limited:
            raise HTTPException(429, "too many requests")
        return None

    app = FastAPI()
    if with_session:
        app.add_middleware(
            SessionMiddleware,
            secret_key="synthetic-session-signing-secret-for-tests-only",
            https_only=not allow_local_http,
            same_site="lax",
            max_age=600,
        )
    app.include_router(
        module["create_google_auth_router"](
            get_organization=organization,
            get_provider=get_provider,
            get_authentication=get_authentication,
            get_flow_store=get_store,
            rate_guard=rate_guard,
            allow_local_http=allow_local_http,
        ),
        prefix="/api/v1",
    )
    return (
        TestClient(app, base_url=base_url),
        provider,
        authentication,
        store,
        context,
        token,
    )


class Tests(unittest.TestCase):
    def test_provider_start_failure_is_sanitized(self):
        client, provider, _authentication, store, _context, _token = build()
        provider.start.side_effect = RuntimeError("private provider diagnostic")
        with client:
            response = client.get("/api/v1/auth/google/start", follow_redirects=False)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private provider diagnostic", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(store.records, {})

    def test_http_denied_before_provider_or_authentication(self):
        for base_url, local in [
            ("http://app.example.com", False),
            ("http://app.example.com", True),
            ("http://localhost", False),
        ]:
            with self.subTest(base_url=base_url, local=local):
                client, provider, authentication, _store, _context, _token = build(
                    base_url=base_url,
                    allow_local_http=local,
                )
                with client:
                    for route in ("/api/v1/auth/google/start", CALLBACK):
                        self.assertEqual(client.get(route).status_code, 400)
                provider.start.assert_not_awaited()
                authentication.login_google.assert_not_awaited()

    def test_explicit_local_http_uses_separate_cookie_names(self):
        client, _provider, _authentication, _store, _context, _token = build(
            base_url="http://localhost",
            allow_local_http=True,
        )
        with client:
            start = client.get("/api/v1/auth/google/start", follow_redirects=False)
            response = client.get(CALLBACK, follow_redirects=False)
        self.assertEqual(start.status_code, 302)
        self.assertIn("account_google_flow_local=", start.headers["set-cookie"])
        self.assertNotIn("Secure", start.headers["set-cookie"])
        self.assertEqual(response.status_code, 303)
        self.assertTrue(
            any(
                cookie.startswith("account_session_local=")
                for cookie in response.headers.get_list("set-cookie")
            )
        )

    def test_missing_middleware_fails_closed(self):
        client, provider, authentication, _store, _context, _token = build(with_session=False)
        with client:
            self.assertEqual(client.get("/api/v1/auth/google/start").status_code, 503)
            self.assertEqual(client.get(CALLBACK).status_code, 400)
        provider.start.assert_not_awaited()
        authentication.login_google.assert_not_awaited()

    def test_rate_limit_blocks_both_routes(self):
        client, provider, authentication, _store, _context, _token = build(limited=True)
        with client:
            for route in ("/api/v1/auth/google/start", CALLBACK):
                self.assertEqual(client.get(route).status_code, 429)
        provider.start.assert_not_awaited()
        authentication.login_google.assert_not_awaited()

    def test_invalid_organization_never_reaches_services(self):
        for invalid in (None, "untrusted", UUID(int=0)):
            with self.subTest(organization=invalid):
                client, provider, authentication, _store, context, _token = build()
                context.organization = invalid
                with client:
                    for route in ("/api/v1/auth/google/start", CALLBACK):
                        self.assertEqual(client.get(route).status_code, 503)
                provider.start.assert_not_awaited()
                authentication.login_google.assert_not_awaited()

    def test_malformed_callbacks_do_not_consume_flow(self):
        queries = [
            "",
            f"state={STATE}",
            f"state={STATE}&code=",
            f"state={STATE}&code=a&code=b",
            "state=short&code=a",
            f"state={STATE}&code=a&error=access_denied",
            f"state={STATE}&code=" + "x" * 4097,
        ]
        for query in queries:
            with self.subTest(query=query[:80]):
                client, _provider, authentication, store, _context, _token = build()
                with client:
                    client.get("/api/v1/auth/google/start", follow_redirects=False)
                    store.consume = AsyncMock(return_value=True)
                    response = client.get("/api/v1/auth/google/callback?" + query)
                self.assertEqual(response.status_code, 400)
                store.consume.assert_not_awaited()
                authentication.login_google.assert_not_awaited()

    def test_provider_redirect_boundaries(self):
        urls = [
            "http://accounts.google.com/?state=" + STATE,
            "https://accounts.google.com:444/?state=" + STATE,
            "https://user@accounts.google.com/?state=" + STATE,
            "https://accounts.google.com/?state=" + STATE + "#fragment",
            "https://accounts.google.com/?state=" + STATE + "&state=duplicate",
            "https://accounts.google.com/?state=short",
        ]
        for url in urls:
            with self.subTest(url=url):
                client, provider, _authentication, store, _context, _token = build()
                provider.start.return_value = RedirectResponse(url)
                with client:
                    response = client.get("/api/v1/auth/google/start", follow_redirects=False)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(store.records, {})

    def test_callback_storage_failure_is_sanitized(self):
        client, _provider, authentication, store, _context, _token = build()
        with client:
            client.get("/api/v1/auth/google/start", follow_redirects=False)
            store.consume = AsyncMock(side_effect=RuntimeError("private storage diagnostic"))
            response = client.get(CALLBACK)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private storage diagnostic", response.text)
        authentication.login_google.assert_not_awaited()

    def test_authentication_failures_are_sanitized_and_cannot_replay(self):
        errors = [
            (HTTPException(status, "private auth diagnostic"), status)
            for status in (401, 403, 409, 503)
        ]
        errors += [
            (HTTPException(500, "private auth diagnostic"), 401),
            (RuntimeError("private auth diagnostic"), 401),
        ]
        for error, expected in errors:
            with self.subTest(error=repr(error)):
                client, _provider, authentication, _store, _context, _token = build()
                authentication.login_google.side_effect = error
                with client:
                    client.get("/api/v1/auth/google/start", follow_redirects=False)
                    binding = client.cookies.get(FLOW_COOKIE)
                    response = client.get(CALLBACK)
                    replay = client.get(CALLBACK, headers={"Cookie": FLOW_COOKIE + "=" + binding})
                self.assertEqual(response.status_code, expected)
                self.assertNotIn("private auth diagnostic", response.text)
                self.assertEqual(response.headers["referrer-policy"], "no-referrer")
                self.assertEqual(replay.status_code, 400)
                authentication.login_google.assert_awaited_once()

    def test_local_http_flag_requires_boolean(self):
        for invalid in (1, "true", None):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                module["create_google_auth_router"](allow_local_http=invalid)

    def test_unconfigured_router_denies_requests(self):
        app = FastAPI()
        app.include_router(
            module["create_google_auth_router"](),
            prefix="/api/v1",
        )
        with TestClient(app) as client:
            response = client.get("/api/v1/auth/google/start")
        self.assertEqual(response.status_code, 503)

    def test_start_sets_secure_browser_binding(self):
        client, _provider, _authentication, store, _context, _token = build()
        with client:
            response = client.get("/api/v1/auth/google/start", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        cookie = response.headers["set-cookie"]
        for fragment in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
            self.assertIn(fragment, cookie)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn(STATE, store.records)

    def test_callback_sets_session_without_token_in_url_and_replay_fails(self):
        client, _provider, authentication, _store, _context, token = build()
        with client:
            client.get("/api/v1/auth/google/start", follow_redirects=False)
            binding = client.cookies.get(FLOW_COOKIE)
            response = client.get(CALLBACK, follow_redirects=False)
            replay = client.get(
                CALLBACK,
                headers={"Cookie": FLOW_COOKIE + "=" + binding},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/")
        self.assertNotIn(token, response.headers["location"])
        self.assertNotIn(token, response.text)
        cookies = response.headers.get_list("set-cookie")
        self.assertTrue(
            any(
                SESSION_COOKIE in cookie and "HttpOnly" in cookie and "Secure" in cookie
                for cookie in cookies
            )
        )
        self.assertEqual(replay.status_code, 400)
        authentication.login_google.assert_awaited_once()

    def test_missing_binding_or_duplicate_state_denied(self):
        client, _provider, authentication, _store, _context, _token = build()
        with client:
            missing = client.get(CALLBACK, follow_redirects=False)
            client.get("/api/v1/auth/google/start", follow_redirects=False)
            duplicate = client.get(CALLBACK + "&state=another", follow_redirects=False)
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(duplicate.status_code, 400)
        authentication.login_google.assert_not_awaited()

    def test_foreign_browser_and_organization_denied(self):
        for foreign_browser in (True, False):
            with self.subTest(foreign_browser=foreign_browser):
                client, _provider, authentication, _store, context, _token = build()
                with client:
                    client.get("/api/v1/auth/google/start", follow_redirects=False)
                    headers = {}
                    if foreign_browser:
                        headers["Cookie"] = FLOW_COOKIE + "=" + secrets.token_urlsafe(32)
                    else:
                        context.organization = OTHER
                    response = client.get(
                        CALLBACK,
                        headers=headers,
                        follow_redirects=False,
                    )
                self.assertEqual(response.status_code, 400)
                authentication.login_google.assert_not_awaited()

    def test_storage_failure_does_not_start_login(self):
        client, _provider, authentication, store, _context, _token = build()
        store.reserve = AsyncMock(side_effect=RuntimeError("private diagnostic"))
        with client:
            response = client.get("/api/v1/auth/google/start", follow_redirects=False)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private diagnostic", response.text)
        authentication.login_google.assert_not_awaited()

    def test_unsafe_provider_redirect_rejected(self):
        client, provider, _authentication, store, _context, _token = build()
        provider.start.return_value = RedirectResponse(
            "https://attacker.example/?state=" + STATE,
        )
        with client:
            response = client.get("/api/v1/auth/google/start", follow_redirects=False)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(store.records, {})

    def test_invalid_session_result_not_installed(self):
        client, _provider, authentication, _store, _context, _token = build()
        authentication.login_google.return_value = "invalid-session"
        with client:
            client.get("/api/v1/auth/google/start", follow_redirects=False)
            response = client.get(CALLBACK, follow_redirects=False)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(
            any(
                cookie.startswith(SESSION_COOKIE + "=")
                for cookie in response.headers.get_list("set-cookie")
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
