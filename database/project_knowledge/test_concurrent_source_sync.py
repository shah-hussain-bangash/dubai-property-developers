"""Test competing PostgreSQL source updates in the isolated database."""

import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TEST_DB = "dubai_ai_knowledge_sync_test"
PROJECT = "dubai-real-estate-ai"
SOURCE_PATH = "core/example.py"

EXPECTED_HASH = (
    "be37dd9a884e425f3bf02a40f7fa2e1961fc349870941cc358830ed2b695333a"
)

NEW_HASH_A = hashlib.sha256(
    b"STEP342_CONCURRENT_UPDATE_A\n"
).hexdigest()

NEW_HASH_B = hashlib.sha256(
    b"STEP342_CONCURRENT_UPDATE_B\n"
).hexdigest()


def query(sql):
    command = [
        "docker", "compose", "exec", "-T", "postgres",
        "psql", "-U", "dubai_ai", "-d", TEST_DB,
        "-X", "-t", "-A", "-v", "ON_ERROR_STOP=1",
        "-c", sql,
    ]

    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def checked_query(sql):
    result = query(sql)

    if result.returncode != 0:
        raise RuntimeError(
            result.stdout + "\n" + result.stderr
        )

    return result.stdout.strip()


def attempt_update(new_hash):
    sql = (
        "SELECT project_knowledge.apply_source_change_test("
        f"'{PROJECT}', "
        f"'{SOURCE_PATH}', "
        f"'{EXPECTED_HASH}', "
        f"'{new_hash}'"
        ");"
    )

    return query(sql)


def main():
    if NEW_HASH_A == NEW_HASH_B:
        raise RuntimeError("Test fingerprints must differ")

    db_name = checked_query("SELECT current_database();")

    if db_name != TEST_DB:
        raise RuntimeError("Unsafe target database")

    current = checked_query(
        "SELECT current_sha256 "
        "FROM project_knowledge.source_current_state "
        "WHERE source_path = 'core/example.py';"
    )

    if current != EXPECTED_HASH:
        raise RuntimeError(
            "Unexpected test fingerprint. Stop before concurrency test."
        )

    counts = checked_query(
        "SELECT "
        "(SELECT COUNT(*) FROM project_knowledge.source_change_events), "
        "(SELECT COUNT(*) FROM project_knowledge.source_current_state);"
    )

    if counts != "4|2":
        raise RuntimeError(
            f"Unexpected test baseline counts: {counts}"
        )

    print("PASS: Isolated database baseline verified")

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(attempt_update, NEW_HASH_A)
        second = executor.submit(attempt_update, NEW_HASH_B)

        results = [first.result(), second.result()]

    successful = []
    rejected = []

    for number, result in enumerate(results, start=1):
        combined = result.stdout + "\n" + result.stderr

        print(f"\nAttempt {number}:")
        print("Exit code:", result.returncode)
        print(combined.strip())

        if result.returncode == 0:
            successful.append(number)
        elif "Source baseline mismatch" in combined:
            rejected.append(number)
        else:
            raise RuntimeError(
                f"Unexpected error from attempt {number}"
            )

    if len(successful) != 1 or len(rejected) != 1:
        raise RuntimeError(
            "Expected exactly one accepted and one rejected update"
        )

    after = checked_query(
        "SELECT current_sha256 "
        "FROM project_knowledge.source_current_state "
        "WHERE source_path = 'core/example.py';"
    )

    if after not in {NEW_HASH_A, NEW_HASH_B}:
        raise RuntimeError("Unexpected final fingerprint")

    final_counts = checked_query(
        "SELECT "
        "(SELECT COUNT(*) FROM project_knowledge.source_change_events), "
        "(SELECT COUNT(*) FROM project_knowledge.source_current_state);"
    )

    if final_counts != "5|2":
        raise RuntimeError(
            f"Unexpected final counts: {final_counts}"
        )

    print("\nPASS: Exactly one concurrent update accepted")
    print("PASS: Competing stale update rejected")
    print("PASS: Only one new change event recorded")
    print("PASS: Current state matches successful update")
    print("PASS: No live application database writes")
    print("Final events and states:", final_counts)
    print("Final fingerprint:", after)


if __name__ == "__main__":
    main()
