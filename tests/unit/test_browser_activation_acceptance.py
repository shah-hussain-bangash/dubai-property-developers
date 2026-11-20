"""Activation and Redis scope/cleanup contracts with fake network clients."""

import asyncio
import runpy
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[2]
M = runpy.run_path(str(ROOT / "scripts/maintenance/browser_activation_acceptance.py"))
FLOW = runpy.run_path(str(ROOT / "core/security/google_oauth_flows.py"))


class Client:
    def __init__(self):
        self.records = {"application:existing": b"preserve"}
        self.lock = asyncio.Lock()
        self.ping = AsyncMock(return_value=True)
        self.aclose = AsyncMock()
        self.calls = []

    async def set(self, key, value, **kwargs):
        self.calls.append(key)
        if key in self.records:
            return None
        self.records[key] = value.encode()
        return True

    async def eval(self, script, count, key, expected):
        self.calls.append(key)
        async with self.lock:
            if self.records.get(key) == expected.encode():
                del self.records[key]
                return 1
            return 0

    async def pttl(self, key):
        return 59999 if key in self.records else -2

    async def get(self, key):
        return self.records.get(key)

    async def exists(self, key):
        return int(key in self.records)

    async def pexpireat(self, key, when):
        self.records.pop(key, None)


class Tests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, client=None):
        client = client or Client()
        return await M["exercise_redis"](
            "redis://localhost:6379/0", FLOW, factory=lambda *args, **kwargs: client
        )

    async def test_all_checks_and_owned_cleanup_preserve_existing_data(self):
        client = Client()
        result = await self.exercise(client)
        self.assertEqual(result["acceptance_status"], "passed_and_cleaned")
        self.assertEqual(len(result["checks"]), 12)
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(client.records, {"application:existing": b"preserve"})
        self.assertTrue(all(key.startswith("step546:") for key in client.calls))
        client.aclose.assert_awaited_once()
        self.assertFalse(result["application_redis_keys_modified"])

    async def test_missing_url_does_not_create_client(self):
        factory = MagicMock()
        result = await M["exercise_redis"](None, FLOW, factory=factory)
        self.assertEqual(result["acceptance_status"], "not_configured")
        factory.assert_not_called()

    async def test_invalid_urls_rejected_without_connection(self):
        for url in (
            "http://localhost",
            "redis://localhost/abc",
            "redis://localhost:bad/0",
            "redis://localhost/0?password=private",
        ):
            factory = MagicMock()
            result = await M["exercise_redis"](url, FLOW, factory=factory)
            self.assertEqual(result["acceptance_status"], "unsupported_configuration")
            factory.assert_not_called()

    async def test_connection_failure_redacts_driver_details(self):
        client = Client()
        client.ping.side_effect = RuntimeError("private credentials")
        result = await self.exercise(client)
        self.assertEqual(result["acceptance_status"], "unavailable_or_failed")
        self.assertNotIn("private credentials", str(result))
        self.assertEqual(client.calls, [])

    async def test_failure_after_reservation_still_cleans_owned_keys(self):
        client = Client()
        client.pttl = AsyncMock(side_effect=RuntimeError("private details"))
        result = await self.exercise(client)
        self.assertEqual(result["acceptance_status"], "unavailable_or_failed")
        self.assertTrue(result["cleanup_confirmed"])
        self.assertEqual(client.records, {"application:existing": b"preserve"})

    async def test_close_failure_blocks_success(self):
        client = Client()
        client.aclose.side_effect = RuntimeError("private close")
        result = await self.exercise(client)
        self.assertEqual(result["acceptance_status"], "connection_cleanup_failed")

    async def test_cleanup_failure_blocks_success(self):
        client = Client()
        client.exists = AsyncMock(side_effect=RuntimeError("private cleanup"))
        result = await self.exercise(client)
        self.assertEqual(result["acceptance_status"], "cleanup_not_confirmed")

    async def test_scope_rejects_arbitrary_keys_and_scripts_with_multiple_keys(self):
        scoped = M["ScopedRedis"](Client())
        with self.assertRaises(ValueError):
            await scoped.set("application:existing", "value", nx=True, ex=60)
        with self.assertRaises(ValueError):
            await scoped.eval("script", 2, "account-auth:google:flow:" + "a" * 64, "value")

    async def test_scope_rejects_no_expiry_or_overwrite(self):
        scoped = M["ScopedRedis"](Client())
        for kwargs in ({"nx": False, "ex": 60}, {"nx": True, "ex": 600}):
            with self.assertRaises(ValueError):
                await scoped.set("account-auth:google:flow:" + "a" * 64, "value", **kwargs)

    async def test_each_runtime_dependency_missing_is_a_blocker(self):
        result = M["activation_status"]({}, {}, {}, {})
        self.assertEqual(len(result["blockers"]), 4)
        self.assertFalse(result["live_activation_ready"])

    async def test_passing_dependencies_do_not_approve_owner_or_activate_routes(self):
        result = M["activation_status"](
            {"configuration_format_ready": True},
            {"required_migrations_registered": True},
            {"inspection_status": "completed", "metadata": {"catalog_metadata_compatible": True}},
            {"acceptance_status": "passed_and_cleaned"},
        )
        self.assertTrue(result["infrastructure_checks_passed"])
        self.assertFalse(result["live_activation_ready"])
        self.assertFalse(result["live_registration_enabled"])
        self.assertEqual(len(result["activation_remaining"]), 3)

    async def test_missing_environment_is_not_echoed(self):
        result = M["activation_status"](
            {"configuration_format_ready": False, "private_secret": "never-return"}, {}, {}, {}
        )
        self.assertNotIn("never-return", str(result))


if __name__ == "__main__":
    unittest.main(verbosity=2)
