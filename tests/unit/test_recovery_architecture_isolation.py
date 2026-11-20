"""Architecture guard for experimental recovery modules.

Ensures ordinary worker modules do not directly import or
reference unsafe experimental recovery entry points.

This is a static dependency guard, not a runtime security
boundary or proof of distributed recovery correctness.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKER_ROOT = ROOT / "apps" / "worker"

EXPERIMENTAL_MODULES = {
    "apps.worker.jobs.redis_recovery",
    "apps.worker.jobs.redis_recovery_evidence",
    "apps.worker.jobs.redis_recovery_fenced",
    "apps.worker.jobs.guarded_recovery_transition",
    "apps.worker.jobs.postgres_redis_recovery_coordinator",
}

RECOVERY_FILES = {
    "redis_recovery.py",
    "redis_recovery_evidence.py",
    "redis_recovery_fenced.py",
    "guarded_recovery_transition.py",
    "postgres_redis_recovery_coordinator.py",
}

PROTECTED_FUNCTIONS = {
    "requeue_reserved_job",
    "acknowledge_stale_reservation",
    "requeue_with_evidence",
    "requeue_with_fencing",
    "GuardedRecoveryTransition",
}


def inspect_source(source: str) -> list[str]:
    """Find forbidden recovery references in Python source."""
    tree = ast.parse(source)
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in EXPERIMENTAL_MODULES:
                    violations.append(f"line {node.lineno}: import {alias.name}")

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""

            if module in EXPERIMENTAL_MODULES:
                violations.append(f"line {node.lineno}: from {module}")

            for alias in node.names:
                if alias.name in PROTECTED_FUNCTIONS:
                    violations.append(f"line {node.lineno}: imported {alias.name}")

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in PROTECTED_FUNCTIONS:
                    violations.append(f"line {node.lineno}: calls {node.func.id}")

            elif isinstance(node.func, ast.Attribute) and node.func.attr in PROTECTED_FUNCTIONS:
                violations.append(f"line {node.lineno}: calls {node.func.attr}")

    return violations


def test_worker_recovery_modules_remain_isolated():
    violations: list[str] = []

    for path in WORKER_ROOT.rglob("*.py"):
        if path.name in RECOVERY_FILES:
            continue

        source = path.read_text(encoding="utf-8")
        findings = inspect_source(source)

        for finding in findings:
            violations.append(f"{path.relative_to(ROOT)}: {finding}")

    assert not violations, (
        "Experimental recovery entry points referenced "
        "outside recovery modules:\n" + "\n".join(violations)
    )


@pytest.mark.parametrize(
    "source",
    [
        "from apps.worker.jobs.redis_recovery import requeue_reserved_job",
        "from apps.worker.jobs.redis_recovery_fenced import requeue_with_fencing",
        "from apps.worker.jobs.guarded_recovery_transition import GuardedRecoveryTransition",
        "requeue_with_evidence()",
        "redis.requeue_reserved_job()",
    ],
)
def test_guard_detects_forbidden_usage(source):
    assert inspect_source(source)


def test_guard_allows_normal_worker_code():
    source = """
import asyncio

async def process_job():
    return "ok"
"""

    assert inspect_source(source) == []
