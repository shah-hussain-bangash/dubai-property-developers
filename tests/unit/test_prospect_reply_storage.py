import json
import tempfile
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, insert, select, text, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.schema import CreateTable

from core.prospect_reply_workflow import ReplyEvent
from database import prospect_reply_storage as db
from database.models.identity import Organization
from database.prospect_research import (
    RevisionConflict,
    UnknownOrganization,
    metadata,
    read_workspace,
    workspaces,
)

STAMP = datetime(2026, 10, 27, 12, tzinfo=UTC)


def profile(key="prospect-one", status="pending"):
    return dict(
        id=key,
        name="Fictional Person",
        company="Fictional Business",
        role="Director",
        country="United Arab Emirates",
        email="",
        phone="",
        whatsapp="",
        whatsappSource="",
        contactResources=[],
        source="https://example.com/profile",
        relevance="Synthetic test only.",
        collectedAt=STAMP.isoformat(),
        status=status,
    )


class ReplyStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "synthetic-replies.sqlite"
        self.engine = create_engine("sqlite:///" + self.path.as_posix())
        metadata.tables["organizations"].create(self.engine)
        workspaces.create(self.engine)
        with self.engine.begin() as conn:
            for slug in ["one", "two"]:
                org = uuid.uuid4()
                conn.execute(
                    insert(Organization.__table__).values(
                        id=org, name="Synthetic " + slug, slug=slug, is_active=True
                    )
                )
                conn.execute(
                    insert(workspaces).values(
                        organization_id=org,
                        revision=1,
                        workspace={"version": 1, "target": {}, "prospects": [profile()]},
                    )
                )
            db.initialize(conn, "one")

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def event(self, key="message-one", kind="reply", text="Synthetic reply only."):
        return ReplyEvent(
            channel="email", provider_event_id=key, kind=kind, received_at=STAMP, text=text
        )

    def record(self, conn, revision=0, event=None, slug="one", prospect="prospect-one"):
        return db.record_incoming(
            conn, slug, revision, prospect, "owner-one", event or self.event(), STAMP
        )

    def test_new_workspace_is_read_only_revision_zero(self):
        with self.engine.begin() as conn:
            saved = db.read_replies(conn, "one")
            self.assertEqual(saved["revision"], 0)
            self.assertEqual(saved["state"]["tasks"], [])
            self.assertEqual(conn.execute(select(db.reply_workspaces)).all(), [])

    def test_reply_task_and_notification_persist_together(self):
        with self.engine.begin() as conn:
            written = self.record(conn)
        with self.engine.begin() as conn:
            stored = db.read_replies(conn, "one")
            self.assertEqual(written, stored)
            self.assertEqual(stored["revision"], 1)
            self.assertEqual(len(stored["state"]["replies"]), 1)
            self.assertEqual(len(stored["state"]["tasks"]), 1)
            self.assertEqual(stored["state"]["notifications"][0]["delivery_state"], "not_connected")
            self.assertEqual(stored["state"]["tasks"][0]["calling_permission"], "unknown")

    def test_survives_database_connection_reopen(self):
        with self.engine.begin() as conn:
            written = self.record(conn)
        self.engine.dispose()
        self.engine = create_engine("sqlite:///" + self.path.as_posix())
        with self.engine.begin() as conn:
            self.assertEqual(db.read_replies(conn, "one"), written)

    def test_event_replay_does_not_increment_revision(self):
        with self.engine.begin() as conn:
            first = self.record(conn)
        with self.engine.begin() as conn:
            replay = self.record(conn, revision=0)
        self.assertEqual(first, replay)

    def test_conflicting_replay_is_not_overwritten(self):
        with self.engine.begin() as conn:
            first = self.record(conn)
        with self.assertRaises(ValueError), self.engine.begin() as conn:
            self.record(conn, 1, self.event(text="Changed duplicate"))
        with self.engine.begin() as conn:
            self.assertEqual(db.read_replies(conn, "one"), first)

    def test_stale_new_event_does_not_write_anything(self):
        with self.engine.begin() as conn:
            first = self.record(conn)
        with self.assertRaises(RevisionConflict), self.engine.begin() as conn:
            self.record(conn, 0, self.event("new-message"))
        with self.engine.begin() as conn:
            self.assertEqual(db.read_replies(conn, "one"), first)

    def test_tenant_isolation_including_duplicate_event_identity(self):
        with self.engine.begin() as conn:
            first = self.record(conn)
        with self.engine.begin() as conn:
            self.assertEqual(db.read_replies(conn, "two")["revision"], 0)
            second = self.record(conn, slug="two")
            self.assertNotEqual(
                first["state"]["replies"][0]["id"], second["state"]["replies"][0]["id"]
            )

    def test_unknown_or_inactive_tenant_is_rejected(self):
        with self.engine.begin() as conn:
            conn.execute(
                update(Organization.__table__)
                .where(Organization.slug == "two")
                .values(is_active=False)
            )
        for slug in ["missing", "two"]:
            with self.assertRaises(UnknownOrganization), self.engine.begin() as conn:
                self.record(conn, slug=slug)

    def test_unknown_and_other_tenant_prospect_rejected(self):
        with self.assertRaises(db.UnknownProspect), self.engine.begin() as conn:
            self.record(conn, prospect="missing")
        with self.engine.begin() as conn:
            org = db.organization(conn, "two")
            conn.execute(
                update(workspaces)
                .where(workspaces.c.organization_id == org)
                .values(
                    workspace={
                        "version": 1,
                        "target": {},
                        "prospects": [profile("other-tenant-only")],
                    }
                )
            )
        with self.assertRaises(db.UnknownProspect), self.engine.begin() as conn:
            self.record(conn, prospect="other-tenant-only")

    def test_archive_flag_comes_from_stored_prospect(self):
        with self.engine.begin() as conn:
            org = db.organization(conn, "one")
            conn.execute(
                update(workspaces)
                .where(workspaces.c.organization_id == org)
                .values(
                    workspace={
                        "version": 1,
                        "target": {},
                        "prospects": [profile(status="archived")],
                    }
                )
            )
            value = self.record(conn)
            self.assertEqual(value["state"]["tasks"], [])
            self.assertEqual(value["state"]["notifications"][0]["callback_blocked"], "archived")

    def test_opt_out_and_callback_cancellation_are_atomic(self):
        with self.engine.begin() as conn:
            self.record(conn)
        with self.engine.begin() as conn:
            stored = self.record(conn, 1, self.event("opt-out", "opt_out"))
            self.assertEqual(stored["revision"], 2)
            self.assertEqual(stored["state"]["tasks"][0]["status"], "cancelled")
            self.assertEqual(len(stored["state"]["suppressions"]), 1)
        with self.engine.begin() as conn:
            stored = self.record(conn, 2, self.event("another-reply"))
            self.assertEqual(len(stored["state"]["tasks"]), 1)
            self.assertEqual(stored["state"]["notifications"][-1]["callback_blocked"], "suppressed")

    def test_transaction_rollback_leaves_no_partial_callback_or_alert(self):
        with self.assertRaises(RuntimeError), self.engine.begin() as conn:
            self.record(conn)
            raise RuntimeError("Synthetic failure before commit")
        with self.engine.begin() as conn:
            self.assertEqual(db.read_replies(conn, "one")["revision"], 0)
            self.assertEqual(conn.execute(select(db.reply_workspaces)).all(), [])

    def test_opt_out_rollback_restores_prior_snapshot(self):
        with self.engine.begin() as conn:
            before = self.record(conn)
        with self.assertRaises(RuntimeError), self.engine.begin() as conn:
            self.record(conn, 1, self.event("stop", "opt_out"))
            raise RuntimeError("Synthetic commit failure")
        with self.engine.begin() as conn:
            self.assertEqual(db.read_replies(conn, "one"), before)

    def test_save_does_not_commit_callers_transaction(self):
        conn = self.engine.connect()
        tx = conn.begin()
        try:
            self.record(conn)
            self.assertTrue(conn.in_transaction())
            tx.rollback()
        finally:
            conn.close()
        with self.engine.begin() as conn:
            self.assertEqual(db.read_replies(conn, "one")["revision"], 0)

    def test_close_task_is_revision_and_owner_scoped(self):
        with self.engine.begin() as conn:
            first = self.record(conn)
        key = first["state"]["tasks"][0]["id"]
        with self.assertRaises(ValueError), self.engine.begin() as conn:
            db.close_callback(conn, "one", 1, "other-owner", key, "completed", "Done.", STAMP)
        with self.assertRaises(RevisionConflict), self.engine.begin() as conn:
            db.close_callback(conn, "one", 0, "owner-one", key, "completed", "Done.", STAMP)
        with self.engine.begin() as conn:
            closed = db.close_callback(
                conn, "one", 1, "owner-one", key, "completed", "Handled by a human.", STAMP
            )
            self.assertEqual(closed["revision"], 2)
            self.assertEqual(closed["state"]["tasks"][0]["status"], "completed")

    def test_iso_datetimes_restore_with_strict_json_validation(self):
        with self.engine.begin() as conn:
            value = self.record(conn)
        restored = db.decode(json.loads(json.dumps(value["state"])), "one")
        self.assertEqual(restored.replies[0].event.received_at, STAMP)

    def test_corrupt_tenant_or_fingerprint_fails_closed(self):
        with self.engine.begin() as conn:
            first = self.record(conn)
        for field, value in [("tenant_id", "two"), ("version", 99)]:
            bad = {**first["state"], field: value}
            with self.assertRaises(ValueError):
                db.decode(bad, "one")
        bad = json.loads(json.dumps(first["state"]))
        bad["replies"][0]["fingerprint"] = "0" * 32
        with self.assertRaises(ValueError):
            db.decode(bad, "one")

    def test_initialization_is_idempotent_and_preserves_existing_records(self):
        with self.engine.begin() as conn:
            workspace = read_workspace(conn, "one")
            written = self.record(conn)
            self.assertEqual(db.initialize(conn, "one"), written)
            self.assertEqual(db.initialize(conn, "one", True), written)
            self.assertEqual(read_workspace(conn, "one"), workspace)

    def test_prospect_workspace_and_permissions_unchanged(self):
        with self.engine.begin() as conn:
            before = read_workspace(conn, "one")
            self.record(conn)
            self.assertEqual(read_workspace(conn, "one"), before)

    def test_mutations_take_organization_lock(self):
        with (
            self.engine.begin() as conn,
            patch.object(db, "organization", wraps=db.organization) as lookup,
        ):
            saved = self.record(conn)
            self.assertTrue(lookup.call_args_list[0].kwargs.get("lock"))
            lookup.reset_mock()
            db.close_callback(
                conn,
                "one",
                1,
                "owner-one",
                saved["state"]["tasks"][0]["id"],
                "cancelled",
                "Human review.",
                STAMP,
            )
            self.assertTrue(lookup.call_args_list[0].kwargs.get("lock"))
        query = select(Organization.id).where(Organization.slug == "one").with_for_update()
        self.assertIn("FOR UPDATE", str(query.compile(dialect=postgresql.dialect())))

    def test_postgresql_schema_has_jsonb_foreign_key_and_revision_check(self):
        ddl = str(CreateTable(db.reply_workspaces).compile(dialect=postgresql.dialect()))
        for fragment in [
            "JSONB",
            "PRIMARY KEY (organization_id)",
            "REFERENCES organizations (id) ON DELETE RESTRICT",
            "revision > 0",
        ]:
            self.assertIn(fragment, ddl)

    def test_check_only_does_not_create_missing_table(self):
        with self.engine.begin() as conn:
            db.reply_workspaces.drop(conn)
        with self.assertRaises(NoSuchTableError), self.engine.begin() as conn:
            db.initialize(conn, "one", True)

    def test_schema_drift_refused(self):
        with self.engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE prospect_reply_workspaces_v1 ADD COLUMN unexpected TEXT")
            )
            with self.assertRaises(ValueError):
                db.check_schema(conn)

    def test_bad_client_revision_rejected_before_save(self):
        for revision in [True, -1, "0", 5]:
            with self.assertRaises(RevisionConflict), self.engine.begin() as conn:
                self.record(conn, revision)


class AccessGuards(unittest.IsolatedAsyncioTestCase):
    async def test_non_local_storage_never_opens_database(self):
        settings = SimpleNamespace(
            is_dev_like=False, enable_dev_routes=True, prospect_storage_enabled=True
        )
        with patch.object(db, "make_engine") as make:
            with self.assertRaises(ValueError):
                await db.access_reply_storage(settings, "one")
            make.assert_not_called()

    async def test_unrecognized_operation_never_opens_database(self):
        settings = SimpleNamespace(
            is_dev_like=True, enable_dev_routes=True, prospect_storage_enabled=True
        )
        with patch.object(db, "make_engine") as make:
            with self.assertRaises(ValueError):
                await db.access_reply_storage(settings, "one", "send")
            make.assert_not_called()
