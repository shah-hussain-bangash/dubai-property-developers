"""Concrete service assembly contracts; external infrastructure remains fake."""

import runpy
import sys
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from fastapi import FastAPI, HTTPException
from sqlalchemy.sql.dml import Insert

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
module = runpy.run_path(str(ROOT / "apps/api/app/browser_services.py"))
Config = module["BrowserServiceConfig"]
build = module["build_browser_service_bindings"]
ORG, OWNER, USER = UUID(int=1), UUID(int=2), UUID(int=3)
GOOGLE = {
    "issuer": "https://accounts.google.com",
    "subject": "synthetic-google-subject",
    "email": "user@example.com",
    "full_name": "Synthetic User",
}


def configuration(**changes):
    values = dict(
        trusted_origin="https://app.example.com",
        organization_id=ORG,
        owner_id=OWNER,
        google_client_id="synthetic-client.apps.googleusercontent.com",
        google_client_secret="synthetic-google-secret-only",
        csrf_secret=b"synthetic-csrf-secret-of-at-least-32-bytes",
        oauth_session_secret="synthetic-oauth-secret-of-at-least-32-bytes",
    )
    values.update(changes)
    return Config(**values)


def setup(config=None, replies=()):
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock()
    transaction.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value = transaction
    responses = []
    for value in replies:
        response = MagicMock()
        response.mappings.return_value.first.return_value = value
        responses.append(response)
    session.execute = AsyncMock(side_effect=responses)
    factory = MagicMock(return_value=session)
    redis = SimpleNamespace(set=AsyncMock(), eval=AsyncMock())
    arguments = dict(
        session_factory=factory,
        redis_client=redis,
        principal_factory=lambda **fields: SimpleNamespace(**fields),
        password_hasher=MagicMock(),
        password_verifier=MagicMock(),
        dummy_hash="synthetic-dummy-hash-not-for-live-use",
        rate_guard=AsyncMock(),
    )
    bundle = build(configuration() if config is None else config, **arguments)
    return bundle, arguments, session


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_concrete_services_share_the_same_dependencies(self):
        bundle, arguments, _session = setup()
        self.assertIs(bundle.authentication._google, bundle.provider)
        self.assertIs(bundle.authentication._sessions, bundle.sessions)
        self.assertIs(bundle.authentication._registration, bundle.registration)
        for service in (
            bundle.sessions,
            bundle.authentication,
            bundle.registration,
            bundle.account_service,
        ):
            self.assertIs(service._factory, arguments["session_factory"])
        self.assertIs(bundle.flow_store._redis, arguments["redis_client"])
        self.assertEqual(
            bundle.provider._redirect_uri, "https://app.example.com/api/v1/auth/google/callback"
        )

    async def test_assembly_performs_no_database_redis_or_password_work(self):
        _bundle, arguments, session = setup()
        arguments["session_factory"].assert_not_called()
        session.execute.assert_not_awaited()
        arguments["redis_client"].set.assert_not_awaited()
        arguments["redis_client"].eval.assert_not_awaited()
        arguments["password_hasher"].assert_not_called()
        arguments["password_verifier"].assert_not_called()

    async def test_installation_is_disabled_by_default(self):
        bundle, _arguments, _session = setup()
        app = FastAPI()
        before = list(app.routes)
        self.assertFalse(bundle.install(app))
        self.assertEqual(app.routes, before)
        self.assertEqual(app.user_middleware, [])

    async def test_explicit_installation_uses_the_reviewed_composition(self):
        bundle, _arguments, _session = setup()
        app = FastAPI()
        self.assertTrue(bundle.install(app, enabled=True))
        self.assertTrue(app.state.browser_auth_installed)
        self.assertEqual(len(app.user_middleware), 1)

    async def test_tenant_and_owner_are_bound_to_server_configuration(self):
        bundle, _arguments, _session = setup()
        self.assertEqual(await bundle.organization_dependency(), ORG)
        self.assertEqual(bundle.account_service.owner_subject(ORG), OWNER)
        self.assertIsNone(bundle.account_service.owner_subject(UUID(int=99)))

    async def test_registration_is_closed_before_password_hashing_or_database(self):
        bundle, arguments, _session = setup()
        with self.assertRaises(HTTPException) as caught:
            await bundle.authentication.register_password(
                ORG,
                email="user@example.com",
                full_name="Synthetic User",
                password="synthetic-password",
            )
        self.assertEqual(caught.exception.status_code, 403)
        arguments["password_hasher"].assert_not_called()
        arguments["session_factory"].assert_not_called()

    async def test_new_google_identity_cannot_create_account_when_registration_closed(self):
        bundle, _arguments, session = setup(replies=[{"id": ORG}, None])
        with self.assertRaises(HTTPException) as caught:
            await bundle.registration.google_account(ORG, verified_identity=GOOGLE)
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(session.execute.await_count, 2)
        self.assertFalse(
            any(isinstance(call.args[0], Insert) for call in session.execute.await_args_list)
        )

    async def test_existing_google_account_can_authenticate_with_registration_closed(self):
        existing = {
            "id": USER,
            "organization_id": ORG,
            "full_name": "Synthetic User",
            "approval_status": "approved",
            "is_active": True,
        }
        bundle, _arguments, session = setup(replies=[{"id": ORG}, existing])
        bundle.provider.complete = AsyncMock(return_value=GOOGLE)
        bundle.sessions.issue_authenticated = AsyncMock(return_value="synthetic-session-result")
        result = await bundle.authentication.login_google(ORG, request=object())
        self.assertEqual(result, "synthetic-session-result")
        bundle.sessions.issue_authenticated.assert_awaited_once_with(
            USER, ORG, auth_method="google"
        )
        self.assertFalse(
            any(isinstance(call.args[0], Insert) for call in session.execute.await_args_list)
        )

    async def test_explicit_registration_flag_selects_the_original_pending_service(self):
        bundle, _arguments, _session = setup(configuration(registration_enabled=True))
        self.assertIs(type(bundle.registration), module["PendingAccountRegistration"])

    async def test_rejected_existing_account_cannot_issue_a_session(self):
        existing = {
            "id": USER,
            "organization_id": ORG,
            "full_name": "Synthetic User",
            "approval_status": "rejected",
            "is_active": True,
        }
        bundle, _arguments, _session = setup(replies=[{"id": ORG}, existing])
        bundle.provider.complete = AsyncMock(return_value=GOOGLE)
        bundle.sessions.issue_authenticated = AsyncMock()
        with self.assertRaises(HTTPException) as caught:
            await bundle.authentication.login_google(ORG, request=object())
        self.assertEqual(caught.exception.status_code, 403)
        bundle.sessions.issue_authenticated.assert_not_awaited()

    async def test_secrets_are_excluded_from_representations(self):
        config = configuration()
        bundle, _arguments, _session = setup(config)
        for secret in (
            config.google_client_secret,
            config.oauth_session_secret,
            config.csrf_secret.decode(),
        ):
            self.assertNotIn(secret, repr(config))
            self.assertNotIn(secret, repr(bundle))

    async def test_configuration_and_bindings_are_frozen(self):
        bundle, _arguments, _session = setup()
        with self.assertRaises(FrozenInstanceError):
            bundle.config.owner_id = USER
        with self.assertRaises(FrozenInstanceError):
            bundle.config = configuration(owner_id=USER)

    async def test_invalid_configuration_rejected(self):
        for changes in (
            {"organization_id": UUID(int=0)},
            {"owner_id": "external-owner"},
            {"trusted_origin": "http://app.example.com"},
            {"trusted_origin": "https://app.example.com/path"},
            {"trusted_origin": "https://app.example.com:bad"},
            {"google_client_secret": ""},
            {"google_client_id": " "},
            {"csrf_secret": b"short"},
            {"oauth_session_secret": "short"},
            {"csrf_secret": b"synthetic-oauth-secret-of-at-least-32-bytes"},
            {"registration_enabled": "false"},
            {"allow_local_http": 1},
            {"session_ttl_seconds": 3601},
            {"flow_ttl_seconds": 601},
            {"session_ttl_seconds": True},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                configuration(**changes)

    async def test_invalid_injected_contract_rejected_before_provider_creation(self):
        _bundle, arguments, _session = setup()
        for field in (
            "session_factory",
            "principal_factory",
            "password_hasher",
            "password_verifier",
            "rate_guard",
            "redis_client",
            "dummy_hash",
        ):
            with self.subTest(field=field):
                invalid = dict(arguments)
                invalid[field] = None
                with patch.dict(build.__globals__, {"GoogleOIDC": MagicMock()}) as namespace:
                    with self.assertRaises(ValueError):
                        build(configuration(), **invalid)
                    namespace["GoogleOIDC"].assert_not_called()

    async def test_ttl_settings_reach_the_correct_services(self):
        bundle, _arguments, _session = setup(
            configuration(session_ttl_seconds=600, flow_ttl_seconds=120)
        )
        self.assertEqual(bundle.sessions._ttl, 600)
        self.assertEqual(bundle.flow_store._ttl, 120)

    async def test_local_http_requires_explicit_loopback_configuration(self):
        config = replace(
            configuration(), trusted_origin="http://localhost:8000", allow_local_http=True
        )
        bundle, _arguments, _session = setup(config)
        self.assertEqual(
            bundle.provider._redirect_uri, "http://localhost:8000/api/v1/auth/google/callback"
        )
        with self.assertRaises(ValueError):
            replace(config, trusted_origin="http://remote.example.com")


if __name__ == "__main__":
    unittest.main(verbosity=2)
