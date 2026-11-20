"""One explicit text-only provider probe; no environment or app activation."""

from __future__ import annotations

import asyncio
import csv
import getpass
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

REPORT = "database/project_knowledge/reports/step613_openai_live_probe_results.json"
ACK = "CONNECTION_OK"


def validate_model(model):
    return (
        isinstance(model, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}", model)
        and not model.lower().startswith(("mock", "sk-", "bearer"))
    )


async def probe(model, key, *, transport=None):
    from core.exceptions.errors import PlatformError
    from core.llm.openai_responses import OpenAIResponsesProvider
    from core.llm.types import ChatMessage, LLMRequest

    result = {
        "outcome": "configuration_rejected",
        "request_attempted": False,
        "request_completed": False,
        "acknowledgement_matched": False,
        "input_tokens": None,
        "output_tokens": None,
        "error_code": None,
    }
    if not validate_model(model):
        result["error_code"] = "invalid_model"
        return result
    try:
        provider = OpenAIResponsesProvider(key, timeout_seconds=30, transport=transport)
    except Exception:
        result["error_code"] = "invalid_key_or_configuration"
        return result
    request = LLMRequest(
        messages=[
            ChatMessage(
                role="user",
                content="This is a fictional software connection check. Return only CONNECTION_OK.",
            )
        ],
        max_output_tokens=256,
    )
    result["request_attempted"] = True
    try:
        response = await provider.complete(request, model=model)
        result.update(
            request_completed=True,
            acknowledgement_matched=response.text.strip() == ACK,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
        result["outcome"] = (
            "live_text_probe_passed"
            if result["acknowledgement_matched"]
            else "live_text_probe_unexpected_acknowledgement"
        )
    except asyncio.CancelledError:
        result.update(outcome="live_text_probe_outcome_unknown", error_code="cancelled")
    except PlatformError as error:
        allowed = {
            "configuration_error",
            "validation_error",
            "integration_not_configured",
            "rate_limited",
            "integration_error",
        }
        result.update(
            outcome="live_text_probe_failed",
            error_code=error.code if error.code in allowed else "provider_error",
        )
    except Exception:
        result.update(outcome="live_text_probe_outcome_unknown", error_code="unexpected_error")
    return result


def _checked(root, name):
    path = root / name
    assert path.resolve().is_relative_to(root)
    for item in (path, *path.parents):
        if item == root.parent:
            break
        assert not item.is_symlink() and not item.is_junction()
    return path


def _preflight(root):
    tool_name = "database/project_knowledge/reports/step613_openai_probe_tool_results.json"
    tool = json.loads(_checked(root, tool_name).read_bytes())
    assert tool["step"] == 613 and tool["acceptance_status"] == "openai_probe_tool_isolated_passed"
    assert tool["inputs_unchanged"] is True and tool["test_count"] == 12
    fingerprints = dict(tool["file_sha256"])
    fingerprints[tool_name] = hashlib.sha256(_checked(root, tool_name).read_bytes()).hexdigest()
    for name, value in fingerprints.items():
        assert hashlib.sha256(_checked(root, name).read_bytes()).hexdigest() == value
    prior = json.loads(
        _checked(
            root, "database/project_knowledge/reports/step612_openai_responses_adapter_results.json"
        ).read_bytes()
    )
    assert (
        prior["step"] == 612
        and prior["acceptance_status"] == "openai_factory_registration_contract_passed"
    )
    queue = _checked(root, "database/project_knowledge/reports/step458_manual_review_queue.csv")
    rows = list(csv.DictReader(queue.read_text(encoding="utf-8-sig").splitlines()))
    holds = {
        "reviewer_decision": "pending",
        "registration_approved": "false",
        "approved_for_live_registration": "false",
        "execute_source": "false",
    }
    assert len(rows) == len({row["source_path"] for row in rows}) == 33
    for row in rows:
        assert all(row[name] == value for name, value in holds.items())
        assert (
            hashlib.sha256(_checked(root, row["source_path"]).read_bytes()).hexdigest()
            == row["sha256"]
        )
    return fingerprints


def main(root=None):
    root = Path(root or sys.argv[1]).resolve(strict=True)
    sys.path.insert(0, str(root))
    fingerprints = _preflight(root)
    report = _checked(root, REPORT)
    if report.exists():
        print("Step 613 already has a live-probe report. Preserved it; no request repeated.")
        print("Evidence:", report)
        return 0
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        print("A local interactive terminal is required for hidden key entry. No request made.")
        return 1
    print("ONE OPTIONAL REAL OPENAI REQUEST; API USAGE MAY BE CHARGED.")
    print("Fixed fictional prompt; at most 256 output tokens; 30-second timeout; no retries.")
    print(
        "Providing a valid model and hidden key starts the request. Blank input or Ctrl+C cancels."
    )
    print("No key is saved, and no environment settings or running services are changed.")
    try:
        model = input("OpenAI model identifier from your API project: ").strip()
        if not model:
            print("Cancelled before a request. No key read or report created.")
            return 0
        if not validate_model(model):
            print("Model identifier rejected before key entry. No request made.")
            return 1
        raw_key = getpass.getpass("OpenAI API key (hidden, not saved): ")
        if not raw_key:
            print("Cancelled before a request. No report created.")
            return 0
        from pydantic import SecretStr

        key = SecretStr(raw_key)
        del raw_key
        assert all(
            hashlib.sha256(_checked(root, name).read_bytes()).hexdigest() == value
            for name, value in fingerprints.items()
        )
        # Reserve before sending, so a crash, interruption or concurrent launch
        # cannot silently issue another paid request on the next invocation.
        run_id = uuid.uuid4().hex
        reservation = {
            "step": 613,
            "run_id": run_id,
            "outcome": "reserved_provider_outcome_not_confirmed",
            "request_attempted": None,
            "maximum_provider_requests": 1,
            "api_key_saved": False,
            "automatic_retries": 0,
            "running_app_activated": False,
        }
        reserved_bytes = (json.dumps(reservation, indent=2) + "\n").encode("utf-8")
        with report.open("xb") as handle:
            handle.write(reserved_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        result = asyncio.run(probe(model, key))
        del key
    except (EOFError, KeyboardInterrupt):
        print(
            "Stopped. If interrupted during a request, provider completion and billing may be unknown."
        )
        return 1
    unchanged = all(
        hashlib.sha256(_checked(root, name).read_bytes()).hexdigest() == value
        for name, value in fingerprints.items()
    )
    evidence = {
        "step": 613,
        "run_id": run_id,
        "verified_at_utc": datetime.now(UTC).isoformat(),
        **result,
        "inputs_unchanged": unchanged,
        "file_sha256": fingerprints,
        "fixed_fictional_prompt": True,
        "maximum_provider_requests": 1,
        "max_output_tokens": 256,
        "automatic_retries": 0,
        "api_key_saved": False,
        "model_identifier_saved": False,
        "response_text_saved": False,
        "environment_files_changed": False,
        "services_rebuilt_or_restarted": False,
        "running_app_activated": False,
        "live_messaging_activated": False,
        "held_sources_hash_verified": 33,
    }
    # Finalize only this invocation's reservation. Any later invocation stops
    # before credential entry and preserves even failed or interrupted evidence.
    assert report.read_bytes() == reserved_bytes
    staging = _checked(root, REPORT + "." + run_id + ".tmp")
    with staging.open("x", encoding="utf-8") as handle:
        json.dump(evidence, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    assert report.read_bytes() == reserved_bytes
    os.replace(staging, report)
    print("Live probe:", result["outcome"])
    print("Request attempted:", result["request_attempted"])
    print("Completed text response:", result["request_completed"])
    print("Expected acknowledgement:", result["acknowledgement_matched"])
    print("Sanitized error code:", result["error_code"] or "none")
    print("Evidence:", report)
    print("App configuration and running services unchanged. Do not share your API key.")
    if result["request_attempted"] and not result["request_completed"]:
        print(
            "An error or timeout does not prove that the provider performed no work. No automatic retry."
        )
    return 0 if result["outcome"] == "live_text_probe_passed" and unchanged else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(
            "Step 613 stopped. Preserve evidence and share only the sanitized output, never the API key."
        )
        sys.exit(1)
