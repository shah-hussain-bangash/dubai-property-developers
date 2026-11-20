# ruff: noqa: S608 -- SQL interpolates only the fixed SOURCE constant in this local concurrency test.
"""Step 351: competing source-sync requests in isolated PostgreSQL."""

import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_DB = "dubai_ai_knowledge_sync_test"
SOURCE = "core/example.py"

EXPECTED = "fa3456bd03a9f62497e084c8d4f94298956d71ed66af96602c0c79af572f190c"

CANDIDATES = [
    hashlib.sha256(b"STEP351_CANDIDATE_A").hexdigest(),
    hashlib.sha256(b"STEP351_CANDIDATE_B").hexdigest(),
]


def execute(sql: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- Trusted local executable and argument list; no shell or request input.
        [  # noqa: S607 -- Local maintenance tool resolves Docker from the operator PATH.
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "dubai_ai",
            "-d",
            TEST_DB,
            "-X",
            "-t",
            "-A",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def read(sql: str) -> str:
    result = execute(sql)

    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)

    return result.stdout.strip()


def attempt(new_hash: str) -> subprocess.CompletedProcess[str]:
    sql = (
        "SELECT project_knowledge.sync_source_test("
        "'dubai-real-estate-ai',"
        f"'{SOURCE}',"
        f"'{EXPECTED}',"
        f"'{new_hash}',"
        "19);"
    )
    return execute(sql)


def main() -> None:
    if read("SELECT current_database();") != TEST_DB:
        raise RuntimeError("Unsafe database target")

    current = read(
        "SELECT current_sha256 "
        "FROM project_knowledge.source_current_state "
        f"WHERE source_path = '{SOURCE}';"
    )

    if current != EXPECTED:
        raise RuntimeError("Unexpected current fingerprint. Stop.")

    before = read(
        "SELECT "
        "(SELECT COUNT(*) FROM project_knowledge.source_references),"
        "(SELECT COUNT(*) FROM project_knowledge.source_versions),"
        "(SELECT COUNT(*) FROM project_knowledge.source_change_events),"
        "(SELECT COUNT(*) FROM project_knowledge.source_current_state);"
    )

    if before != "4|6|10|4":
        raise RuntimeError(f"Unexpected baseline: {before}")

    if len(set([*CANDIDATES, EXPECTED])) != 3:
        raise RuntimeError("Invalid test fingerprints")

    print("PASS: Test database and baseline verified")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(attempt, h) for h in CANDIDATES]
        results = [f.result() for f in futures]

    winners = []
    rejected = []

    for index, result in enumerate(results):
        output = result.stdout + result.stderr
        print(f"\nCandidate {index + 1}:")
        print(output.strip())

        if result.returncode == 0:
            winners.append(index)
        elif "Source baseline mismatch" in output:
            rejected.append(index)
        else:
            raise RuntimeError("Unexpected synchronization error")

    if len(winners) != 1 or len(rejected) != 1:
        raise RuntimeError("Expected one successful and one rejected update")

    after = read(
        "SELECT "
        "(SELECT COUNT(*) FROM project_knowledge.source_references),"
        "(SELECT COUNT(*) FROM project_knowledge.source_versions),"
        "(SELECT COUNT(*) FROM project_knowledge.source_change_events),"
        "(SELECT COUNT(*) FROM project_knowledge.source_current_state);"
    )

    final_hash = read(
        "SELECT current_sha256 "
        "FROM project_knowledge.source_current_state "
        f"WHERE source_path = '{SOURCE}';"
    )

    if after != "4|7|11|4":
        raise RuntimeError(f"Unexpected final counts: {after}")

    if final_hash != CANDIDATES[winners[0]]:
        raise RuntimeError("Final fingerprint differs from winner")

    print("\nPASS: Exactly one update committed")
    print("PASS: Competing stale update rejected")
    print("PASS: Exactly one new version and event recorded")
    print("PASS: Final fingerprint matches winning candidate")
    print("Final counts:", after)
    print("Final fingerprint:", final_hash)


if __name__ == "__main__":
    main()
