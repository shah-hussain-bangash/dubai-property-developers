"""Offline tests: simulated local API and clock; no provider or source page requests."""

import copy
import importlib.util
import io
import json
import os
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location(
    "prospect_runner", Path(__file__).resolve().parents[2] / "scripts/run_prospect_research_job.py"
)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
NOW = datetime(2026, 10, 27, 19, 59, 30, tzinfo=UTC)
JOB = "test-job"


def saved(status="ready", **fields):
    state = dict(
        version=1,
        id=JOB,
        tenant_id="test-org",
        target=500,
        status=status,
        cursor=0,
        provider_attempts=0,
        resume_at=None,
        queries=[{}] * 60,
        candidates=[],
    )
    state.update(fields)
    return {"revision": 1, "state": state}


class Clock:
    def __init__(self):
        self.stamp = NOW
        self.sleeps = []

    def now(self):
        return self.stamp

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.stamp += timedelta(seconds=seconds)


class API:
    def __init__(self, value=None):
        self.value = value or saved()
        self.calls = []
        self.reads = 0
        self.cap_checks = 0
        self.on_read = None
        self.on_advance = None

    def read(self, job, tenant):
        self.reads += 1
        if self.on_read:
            self.on_read(self)
        return r.validate_saved(copy.deepcopy(self.value), job, tenant)

    def capabilities(self):
        self.cap_checks += 1

    def advance(self, job, revision, tenant):
        self.calls.append((job, revision, tenant))
        if self.on_advance:
            return self.on_advance(self)
        self.value["revision"] += 2
        self.value["state"]["cursor"] += 1
        self.value["state"]["provider_attempts"] += 1
        self.value["state"]["candidates"].append({})
        self.value["state"].update(status="ready", resume_at=None)
        return copy.deepcopy(self.value)


class RunnerTests(unittest.TestCase):
    def run_job(self, api, budget=1, clock=None):
        clock = clock or Clock()
        messages = []
        r.run(api, JOB, budget, now=clock.now, sleep=clock.sleep, emit=messages.append)
        return clock, messages

    def test_waits_until_gst_midnight_then_runs_once(self):
        api = API(saved("quota_wait", resume_at="2026-10-28T00:00:00+04:00"))
        clock, _ = self.run_job(api)
        self.assertEqual(clock.sleeps, [30])
        self.assertEqual(len(api.calls), 1)
        self.assertEqual(api.calls[0], (JOB, 1, "test-org"))

    def test_two_attempts_are_in_different_dubai_days(self):
        api = API()
        clock = Clock()
        times = []

        def advance(a):
            times.append(clock.now())
            a.value["revision"] += 2
            a.value["state"]["cursor"] += 1
            a.value["state"]["provider_attempts"] += 1
            return copy.deepcopy(a.value)

        api.on_advance = advance
        self.run_job(api, 2, clock)
        self.assertEqual(len(times), 2)
        self.assertNotEqual(times[0].astimezone(r.GST).date(), times[1].astimezone(r.GST).date())
        self.assertEqual(api.cap_checks, 2)

    def test_shared_quota_denial_waits_without_counting_a_provider_attempt(self):
        api = API()
        clock = Clock()

        def advance(a):
            a.value["revision"] += 1
            if len(a.calls) == 1:
                a.value["state"].update(status="quota_wait", resume_at="2026-10-28T00:00:00+04:00")
            else:
                a.value["state"].update(
                    status="ready", resume_at=None, cursor=1, provider_attempts=1
                )
            return copy.deepcopy(a.value)

        api.on_advance = advance
        self.run_job(api, clock=clock)
        self.assertEqual(len(api.calls), 2)
        self.assertEqual(clock.sleeps, [30])

    def test_dashboard_pause_is_seen_while_waiting(self):
        api = API(saved("quota_wait", resume_at="2026-10-29T00:00:00+04:00"))
        api.on_read = lambda a: a.value["state"].update(status="paused") if a.reads == 2 else None
        clock, _ = self.run_job(api)
        self.assertEqual(clock.sleeps, [60])
        self.assertEqual(api.calls, [])

    def test_terminal_states_never_advance(self):
        for status in [
            "paused",
            "request_uncertain",
            "queries_exhausted",
            "cancelled",
            "error",
            "completed",
        ]:
            with self.subTest(status=status):
                api = API(saved(status, target=1, candidates=[{}] if status == "completed" else []))
                self.run_job(api)
                self.assertEqual(api.calls, [])

    def test_uncertain_post_result_stops_without_retry(self):
        api = API()

        def advance(a):
            a.value["revision"] += 1
            a.value["state"].update(status="request_uncertain", cursor=1, provider_attempts=1)
            return copy.deepcopy(a.value)

        api.on_advance = advance
        self.run_job(api, 60)
        self.assertEqual(len(api.calls), 1)

    def test_post_failure_has_no_automatic_retry(self):
        api = API()

        def fail(a):
            raise r.RunnerStopped("Outcome uncertain")

        api.on_advance = fail
        with self.assertRaises(r.RunnerStopped):
            self.run_job(api, 60)
        self.assertEqual(len(api.calls), 1)

    def test_get_failure_has_no_mutation(self):
        api = API()
        api.read = Mock(side_effect=r.RunnerStopped("Unavailable"))
        with self.assertRaises(r.RunnerStopped):
            self.run_job(api)
        self.assertEqual(api.calls, [])

    def test_invalid_capabilities_stop_before_action(self):
        api = API()
        api.capabilities = Mock(side_effect=r.RunnerStopped("Wrong budget"))
        with self.assertRaises(r.RunnerStopped):
            self.run_job(api)
        self.assertEqual(api.calls, [])

    def test_no_progress_is_not_retried(self):
        api = API()
        api.on_advance = lambda a: {"revision": 2, "state": copy.deepcopy(a.value["state"])}
        with self.assertRaises(r.RunnerStopped):
            self.run_job(api)
        self.assertEqual(len(api.calls), 1)

    def test_stale_response_is_not_retried(self):
        api = API()
        api.on_advance = lambda a: copy.deepcopy(a.value)
        with self.assertRaises(r.RunnerStopped):
            self.run_job(api)
        self.assertEqual(len(api.calls), 1)

    def test_organization_switch_stops(self):
        api = API(saved("quota_wait", resume_at="2026-10-29T00:00:00+04:00"))
        api.on_read = lambda a: a.value["state"].update(tenant_id="other") if a.reads == 2 else None
        with self.assertRaises(r.RunnerStopped):
            self.run_job(api)
        self.assertEqual(api.calls, [])

    def test_attempt_budget_is_bounded(self):
        for value in [0, 101, True, "60"]:
            with self.subTest(value=value), self.assertRaises(r.RunnerStopped):
                self.run_job(API(), value)

    def test_plan_validation(self):
        changes = [
            dict(id="other"),
            dict(tenant_id=""),
            dict(status="running"),
            dict(target=501),
            dict(cursor=61),
            dict(provider_attempts=1),
            dict(queries=[]),
            dict(status="quota_wait"),
            dict(resume_at="2026-10-28T00:00:00"),
            dict(candidates=[{}] * 501),
        ]
        for change in changes:
            value = saved(**change)
            with self.subTest(change=str(change)[:60]), self.assertRaises(r.RunnerStopped):
                r.validate_saved(value, JOB)

    def test_utc_boundary_is_dubai_midnight(self):
        result = r.next_midnight(NOW)
        self.assertEqual(result.isoformat(), "2026-10-28T00:00:00+04:00")

    def test_no_repeated_wait_messages(self):
        api = API(saved("quota_wait", resume_at="2026-10-28T00:02:00+04:00"))
        _, messages = self.run_job(api)
        self.assertEqual(sum(x.startswith("Waiting until") for x in messages), 1)

    @unittest.skipUnless(os.name == "nt", "Windows named mutex")
    def test_duplicate_runner_lock_and_release(self):
        job = "offline-test-" + str(uuid.uuid4())
        with r.single_runner(job), self.assertRaises(r.RunnerStopped), r.single_runner(job):
            pass
        with r.single_runner(job):
            pass


class HTTPTests(unittest.TestCase):
    def api(self, value, status=200, media="application/json"):
        api = r.LocalAPI()
        response = Mock()
        response.status = status
        response.headers.get_content_type.return_value = media
        response.read.return_value = json.dumps(value).encode()
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        api.opener = Mock()
        api.opener.open.return_value = context
        return api

    def envelope(self, **fields):
        return dict(storage="postgresql", outreach_enabled=False, scheduled=False, **fields)

    def test_action_body_is_only_revision_and_advance_to_loopback(self):
        api = self.api(self.envelope(batch=saved()))
        api.advance(JOB, 7, "test-org")
        req = api.opener.open.call_args.args[0]
        self.assertEqual(req.full_url, r.BASE + "/batches/test-job/actions")
        self.assertEqual(json.loads(req.data), {"action": "advance", "revision": 7})
        self.assertFalse(req.has_header("Authorization"))
        self.assertNotIn("key", req.full_url)

    def test_http_error_body_never_printed_or_retried(self):
        api = r.LocalAPI()
        api.opener = Mock()
        api.opener.open.side_effect = r.HTTPError(
            r.BASE, 409, "PRIVATE_SENTINEL", {}, io.BytesIO(b"PRIVATE_SENTINEL")
        )
        with self.assertRaises(r.RunnerStopped) as error:
            api.read(JOB)
        self.assertNotIn("PRIVATE_SENTINEL", str(error.exception))
        self.assertEqual(api.opener.open.call_count, 1)

    def test_redirect_refused(self):
        with self.assertRaises(r.RunnerStopped):
            r.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com")

    def test_arbitrary_path_refused(self):
        api = self.api({})
        for path in ["https://example.com", "/batches/../workspace", "/discover"]:
            with self.assertRaises(r.RunnerStopped):
                api.request(path)
        api.opener.open.assert_not_called()

    def test_malformed_or_oversize_response_refused(self):
        for raw in [b"{", b"[]", b"x" * 5_000_001]:
            api = self.api({})
            api.opener.open.return_value.__enter__.return_value.read.return_value = raw
            with self.assertRaises(r.RunnerStopped):
                api.request("/batches")

    def test_provenance_refused(self):
        for key, value in [("storage", "memory"), ("outreach_enabled", True), ("scheduled", True)]:
            payload = self.envelope(batch=saved())
            payload[key] = value
            with self.assertRaises(r.RunnerStopped):
                self.api(payload).read(JOB)

    def test_only_limit_one_enabled_serpapi_allowed(self):
        payload = dict(
            provider="serpapi",
            enabled=True,
            daily_limit=1,
            outreach_enabled=False,
            automatic_collection=False,
        )
        self.api(payload).capabilities()
        for key, value in [
            ("daily_limit", 2),
            ("daily_limit", True),
            ("provider", "disabled"),
            ("enabled", False),
            ("outreach_enabled", True),
        ]:
            bad = dict(payload)
            bad[key] = value
            with self.assertRaises(r.RunnerStopped):
                self.api(bad).capabilities()

    def test_list_is_read_only(self):
        payload = self.envelope(batches=[dict(id=JOB, status="ready", count=0, target=500)])
        api = self.api(payload)
        self.assertEqual(len(api.jobs()), 1)
        req = api.opener.open.call_args.args[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertIsNone(req.data)
