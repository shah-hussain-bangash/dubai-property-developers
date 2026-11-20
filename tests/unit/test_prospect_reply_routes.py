import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.prospect_reply_workflow import (
    ConfirmedProspectLink,
    ReplyEvent,
    ReplyWorkflow,
    record_reply,
)
from database.prospect_reply_storage import UnknownProspect
from database.prospect_research import RevisionConflict


class ReplyRoutes(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from apps.api.app.api.v1.routes import prospect_replies
        from apps.api.app.main import create_app
        from core.config.settings import Settings
        from workflows.runtime import build_runtime

        self.route = prospect_replies
        settings = Settings(
            _env_file=None,
            environment="test",
            auth_mode="dev",
            enable_dev_routes=True,
            prospect_storage_enabled=True,
            lead_store_backend="memory",
            workflow_store_backend="memory",
            integrations_mode="mock",
            llm_provider="mock",
            rate_limit_per_minute=1000,
        )
        self.app = create_app(settings, build_runtime(settings))
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.path = "/api/v1/prospect-research/replies"
        self.blank = {
            "revision": 0,
            "state": ReplyWorkflow(tenant_id="demo-org").model_dump(mode="json"),
        }
        self.body = dict(
            revision=0,
            prospect_id="test-prospect",
            event_id="event-one",
            channel="email",
            kind="reply",
            received_at="2026-01-01T00:00:00+04:00",
            text="Synthetic reply only.",
            confirmed=True,
        )

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_load_is_read_only_and_private(self):
        fake = AsyncMock(return_value=self.blank)
        with patch.object(self.route, "access_reply_storage", fake):
            response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(fake.call_args.args[1:3], ("demo-org", "read"))
        self.assertFalse(response.json()["inbox_connected"])
        self.assertFalse(response.json()["notifications_delivered"])

    def test_record_uses_server_tenant_owner_and_manual_event_identity(self):
        fake = AsyncMock(return_value=self.blank)
        with patch.object(self.route, "access_reply_storage", fake):
            response = self.client.post(self.path, json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake.call_args.args[1:3], ("demo-org", "record"))
        self.assertEqual(fake.call_args.kwargs["owner_id"], "dev-user")
        self.assertEqual(fake.call_args.kwargs["event"].provider_event_id, "manual-event-one")

    def test_owner_and_tenant_body_injection_refused(self):
        with patch.object(self.route, "access_reply_storage", AsyncMock()) as fake:
            for field in ["owner_id", "tenant_id", "send_call"]:
                self.assertEqual(
                    self.client.post(self.path, json={**self.body, field: "other"}).status_code, 422
                )
        fake.assert_not_called()

    def test_confirmation_required(self):
        with patch.object(self.route, "access_reply_storage", AsyncMock()) as fake:
            for value in [False, 1, "true"]:
                self.assertEqual(
                    self.client.post(self.path, json={**self.body, "confirmed": value}).status_code,
                    422,
                )
        fake.assert_not_called()

    def test_viewer_cannot_record_or_close(self):
        with patch.object(self.route, "access_reply_storage", AsyncMock()) as fake:
            self.assertEqual(
                self.client.post(
                    self.path, headers={"X-Dev-Roles": "viewer"}, json=self.body
                ).status_code,
                403,
            )
            self.assertEqual(
                self.client.post(
                    self.path + "/close-task", headers={"X-Dev-Roles": "viewer"}, json={}
                ).status_code,
                403,
            )
        fake.assert_not_called()

    def test_origin_and_request_size_limits(self):
        with patch.object(self.route, "access_reply_storage", AsyncMock()) as fake:
            self.assertEqual(
                self.client.post(
                    self.path, headers={"Origin": "https://example.com"}, json=self.body
                ).status_code,
                403,
            )
            self.assertEqual(self.client.post(self.path, content=b"x" * 50001).status_code, 413)
        fake.assert_not_called()

    def test_invalid_timezone_future_time_and_blank_reply_refused(self):
        with patch.object(self.route, "access_reply_storage", AsyncMock()) as fake:
            for change in [
                {"received_at": "2026-01-01T00:00:00"},
                {"received_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
                {"text": "   "},
                {"kind": "investor_confirmed"},
            ]:
                self.assertEqual(
                    self.client.post(self.path, json={**self.body, **change}).status_code, 422
                )
        fake.assert_not_called()

    def test_revision_conflict_is_not_retried(self):
        fake = AsyncMock(side_effect=RevisionConflict())
        with patch.object(self.route, "access_reply_storage", fake):
            response = self.client.post(self.path, json=self.body)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(fake.call_count, 1)

    def test_unknown_prospect_is_not_guessed(self):
        with patch.object(
            self.route, "access_reply_storage", AsyncMock(side_effect=UnknownProspect())
        ):
            response = self.client.post(self.path, json=self.body)
        self.assertEqual(response.status_code, 422)

    def test_database_failure_never_exposes_raw_diagnostic(self):
        with patch.object(
            self.route,
            "access_reply_storage",
            AsyncMock(side_effect=RuntimeError("PRIVATE_SENTINEL")),
        ):
            response = self.client.get(self.path)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("PRIVATE_SENTINEL", response.text)

    def test_close_is_server_owner_scoped(self):
        fake = AsyncMock(return_value=self.blank)
        with patch.object(self.route, "access_reply_storage", fake):
            response = self.client.post(
                self.path + "/close-task",
                json=dict(revision=1, task_id="a" * 32, status="completed", note="Human reviewed."),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake.call_args.args[2], "close")
        self.assertEqual(fake.call_args.kwargs["owner_id"], "dev-user")

    def test_projection_bounds_history_and_never_exposes_provider_ids(self):
        state = ReplyWorkflow(tenant_id="demo-org")
        stamp = datetime.now(UTC)
        link = ConfirmedProspectLink(
            tenant_id="demo-org", prospect_id="test-prospect", owner_id="dev-user", confirmed=True
        )
        for i in range(51):
            state = record_reply(
                state,
                "demo-org",
                link,
                ReplyEvent(
                    channel="email",
                    provider_event_id="private-" + str(i),
                    kind="reply",
                    received_at=stamp,
                    text="x" * 1000,
                ),
                stamp,
            )
        projected = self.route.project(
            {"revision": 51, "state": state.model_dump(mode="json")},
            SimpleNamespace(subject="dev-user"),
        )
        self.assertEqual(len(projected["recent_replies"]), 50)
        self.assertEqual(len(projected["recent_replies"][0]["text"]), 500)
        self.assertNotIn("provider_event_id", str(projected))
        self.assertNotIn("event_ids", projected["tasks"][0])

    def test_manual_opt_out_is_passed_without_starting_callback_or_delivery(self):
        fake = AsyncMock(return_value=self.blank)
        with patch.object(self.route, "access_reply_storage", fake):
            response = self.client.post(self.path, json={**self.body, "kind": "opt_out"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake.call_args.kwargs["event"].kind, "opt_out")
        self.assertFalse(response.json()["outreach_enabled"])
