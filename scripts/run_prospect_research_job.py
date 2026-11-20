"""Opt-in foreground runner for one saved local research job. Standard library only."""

import argparse
import ctypes
import json
import os
import re
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

BASE = "http://127.0.0.1:8000/api/v1/prospect-research"
GST = timezone(timedelta(hours=4))
STATUSES = {
    "ready",
    "quota_wait",
    "paused",
    "request_uncertain",
    "completed",
    "queries_exhausted",
    "cancelled",
    "error",
}


class RunnerStopped(Exception):
    """Only fixed, safe messages are shown to the terminal."""


def require(value, message="Saved job response is invalid. Stopped without retry."):
    if not value:
        raise RunnerStopped(message)


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9-]{1,80}", value) is not None)
    return value


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def date(value):
    require(isinstance(value, str))
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        raise RunnerStopped("Saved quota date is invalid. Stopped without retry.") from None
    require(result.tzinfo is not None and result.utcoffset() is not None)
    return result


def validate_saved(value, expected_id, expected_tenant=None):
    require(isinstance(value, dict))
    state = value.get("state")
    require(isinstance(state, dict) and integer(value.get("revision"), 1, 2**53))
    require(state.get("version") == 1 and state.get("id") == expected_id)
    tenant = state.get("tenant_id")
    require(isinstance(tenant, str) and 1 <= len(tenant) <= 100)
    require(
        expected_tenant is None or tenant == expected_tenant,
        "Organization changed. Runner stopped.",
    )
    require(state.get("status") in STATUSES and integer(state.get("target"), 1, 500))
    queries, candidates = state.get("queries"), state.get("candidates")
    require(isinstance(queries, list) and 1 <= len(queries) <= 100)
    require(isinstance(candidates, list) and len(candidates) <= state["target"])
    require(integer(state.get("cursor"), 0, len(queries)))
    require(integer(state.get("provider_attempts"), 0, state["cursor"]))
    if state.get("resume_at") is not None:
        date(state["resume_at"])
    require(state["status"] != "quota_wait" or state.get("resume_at") is not None)
    require(state["status"] != "completed" or len(candidates) == state["target"])
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RunnerStopped("Local API redirected the request. Runner stopped.")


class LocalAPI:
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, path, body=None):
        # No arbitrary URL, proxy, credentials, provider key, cookies or redirects.
        require(
            path in {"/batches", "/discovery-capabilities"}
            or re.fullmatch(r"/batches/[a-zA-Z0-9-]{1,80}(/actions)?", path)
        )
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = Request(  # noqa: S310 -- Fixed loopback HTTP endpoint; redirects are disabled or this is a local acceptance script.
            BASE + path,
            data=data,
            headers={
                "Accept": "application/json",
                "Cache-Control": "no-store",
                **({"Content-Type": "application/json"} if data else {}),
            },
        )
        try:
            with self.opener.open(req, timeout=90) as response:
                require(
                    response.status == 200
                    and response.headers.get_content_type() == "application/json"
                )
                raw = response.read(5_000_001)
                require(len(raw) <= 5_000_000)
                value = json.loads(raw)
                require(isinstance(value, dict))
                return value
        except RunnerStopped:
            raise
        except HTTPError as error:
            error.close()
            raise RunnerStopped(
                "Local API rejected the request. Reload the job in the dashboard; no automatic retry."
            ) from None
        except Exception:
            raise RunnerStopped(
                "Local API outcome could not be confirmed. Reload the job before restarting; no automatic retry."
            ) from None

    def capabilities(self):
        value = self.request("/discovery-capabilities")
        require(
            value.get("provider") == "serpapi"
            and value.get("enabled") is True
            and type(value.get("daily_limit")) is int
            and value["daily_limit"] == 1
            and value.get("outreach_enabled") is False
            and value.get("automatic_collection") is False,
            "A configured local SerpApi connection with daily limit 1 is required. Settings were not changed.",
        )

    def envelope(self, path, body=None):
        value = self.request(path, body)
        require(
            value.get("storage") == "postgresql"
            and value.get("outreach_enabled") is False
            and value.get("scheduled") is False
        )
        return value

    def jobs(self):
        jobs = self.envelope("/batches").get("batches")
        require(isinstance(jobs, list) and len(jobs) <= 20)
        for job in jobs:
            require(isinstance(job, dict))
            identifier(job.get("id"))
            require(
                job.get("status") in STATUSES
                and integer(job.get("count"), 0, 500)
                and integer(job.get("target"), 1, 500)
            )
        require(len({job["id"] for job in jobs}) == len(jobs))
        return jobs

    def read(self, job_id, tenant=None):
        return validate_saved(
            self.envelope("/batches/" + identifier(job_id)).get("batch"), job_id, tenant
        )

    def advance(self, job_id, revision, tenant):
        return validate_saved(
            self.envelope(
                "/batches/" + identifier(job_id) + "/actions",
                {"action": "advance", "revision": revision},
            ).get("batch"),
            job_id,
            tenant,
        )


@contextmanager
def single_runner(job_id):
    require(os.name == "nt", "This launcher requires Windows.")
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # Global namespace prevents duplicates across Windows login sessions.
    name = (
        "Global\\DubaiProspectRunner-"
        + sha256((BASE + "|" + identifier(job_id)).encode()).hexdigest()
    )
    handle = kernel.CreateMutexW(None, False, name)
    error = ctypes.get_last_error()
    require(bool(handle), "Could not obtain the local runner lock. No job started.")
    try:
        require(error != 183, "Another runner already has this job open. No second runner started.")
        yield
    finally:
        kernel.CloseHandle(handle)


def next_midnight(stamp):
    return (stamp.astimezone(GST) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def run(api, job_id, max_attempts=60, now=lambda: datetime.now(UTC), sleep=time.sleep, emit=print):
    require(integer(max_attempts, 1, 100), "Attempt budget must be from 1 to 100.")
    tenant, previous, attempts, local_wait = None, None, 0, None
    while True:
        saved = api.read(job_id, tenant)
        state = saved["state"]
        tenant = state["tenant_id"]
        fingerprint = (
            state["status"],
            len(state["candidates"]),
            state["cursor"],
            state["resume_at"],
        )
        if fingerprint != previous:
            emit(
                f"Job {job_id}: {state['status']}; {len(state['candidates'])}/{state['target']} source candidates; {state['cursor']}/{len(state['queries'])} queries processed."
            )
            if state["status"] == "quota_wait":
                emit(
                    "Waiting until "
                    + date(state["resume_at"]).astimezone(GST).strftime("%d/%m/%Y %H:%M GST")
                    + ". Keep this terminal open and the computer awake."
                )
            previous = fingerprint
        if state["status"] not in {"ready", "quota_wait"}:
            emit(
                "Runner stopped. Review the saved job in the dashboard. No automatic resume or retry."
            )
            return
        if attempts >= max_attempts:
            emit("Runner attempt budget reached. Saved job retained; runner stopped.")
            return
        stamp = now()
        require(stamp.tzinfo is not None)
        waits = [
            x
            for x in (local_wait, date(state["resume_at"]) if state["resume_at"] else None)
            if x is not None
        ]
        due = max(waits) if waits else stamp
        if stamp < due:
            sleep(min(60, max(1, (due - stamp).total_seconds())))
            continue
        api.capabilities()  # Revalidate the unchanged daily limit immediately before each action.
        result = api.advance(job_id, saved["revision"], tenant)
        after = result["state"]
        require(
            result["revision"] > saved["revision"], "Job did not advance. Stopped without retry."
        )
        delta = after["provider_attempts"] - state["provider_attempts"]
        require(
            delta in {0, 1} and after["cursor"] >= state["cursor"],
            "Unexpected job progress. Runner stopped.",
        )
        if delta:
            attempts += delta
            # Extra in-process pacing, in addition to the server's shared Redis quota.
            local_wait = next_midnight(now())
            emit(
                "One search attempt processed. Next automatic attempt is no earlier than the next Dubai day."
            )
        elif after["status"] in {"ready", "quota_wait"}:
            require(
                after["status"] == "quota_wait" and date(after["resume_at"]) > now(),
                "No progress or future quota time. Stopped without retry.",
            )
        # Always reload authoritative state, including pause/cancel performed in the dashboard.


def main():
    parser = argparse.ArgumentParser(
        description="Run one saved local research job while this terminal remains open."
    )
    parser.add_argument("--job-id")
    parser.add_argument("--max-attempts", type=int, default=60)
    parser.add_argument("--list", action="store_true", help="Read job summaries only; no search.")
    args = parser.parse_args()
    api = LocalAPI()
    if args.list or not args.job_id:
        jobs = api.jobs()
        for index, job in enumerate(jobs, 1):
            print(
                f"{index}. {job['id']} | {job['status']} | {job['count']}/{job['target']} source candidates"
            )
        if args.list:
            return
        require(bool(jobs), "No saved job found. Create a research job in the dashboard first.")
        choice = input("Enter the job number to start, or press Enter to cancel: ").strip()
        if not choice:
            print("Cancelled. No job started.")
            return
        require(
            choice.isascii() and choice.isdigit() and 1 <= int(choice) <= len(jobs),
            "Invalid job number. No job started.",
        )
        job_id = jobs[int(choice) - 1]["id"]
    else:
        job_id = identifier(args.job_id)
    print(
        "Starting one saved job. Automatic searches use the existing provider allowance: at most one per Dubai day."
    )
    print(
        "Keep this terminal open and the computer awake. Ctrl+C stops this runner; dashboard Pause/Cancel is checked at least every 60 seconds while waiting."
    )
    print(
        "No Windows scheduled task is installed. No automatic restart after sleep shutdown, terminal closure or failure. No contacts saved or messages sent."
    )
    with single_runner(job_id):
        run(api, job_id, args.max_attempts)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print(
            "\nRunner stopped. An in-flight request may finish on the server. Reload saved job state before restarting."
        )
    except RunnerStopped as error:
        print(str(error))
        raise SystemExit(1) from None
    except Exception:
        print(
            "Runner stopped unexpectedly. Reload the saved job in the dashboard. No automatic retry; no private error details displayed."
        )
        raise SystemExit(1) from None
