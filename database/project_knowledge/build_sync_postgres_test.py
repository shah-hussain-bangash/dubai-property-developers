"""Build synthetic source-sync SQL for an isolated PostgreSQL test."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "database" / "project_knowledge"
DESTINATION = FOLDER / "009_synthetic_source_sync.sql"

OLD_CONTENT = b"ORIGINAL_TEST_CONTENT = 1\n"
NEW_CONTENT = b"UPDATED_TEST_CONTENT = 2\n"
ADDED_CONTENT = b"NEW_TEST_MODULE = True\n"


def fingerprint(content):
    return hashlib.sha256(content).hexdigest()


def run_tool(path):
    result = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{path.name} failed:\n"
            f"{result.stdout}\n{result.stderr}"
        )

    print(result.stdout)


def main():
    if DESTINATION.exists():
        raise RuntimeError(
            "Synthetic SQL already exists. Do not overwrite."
        )

    with tempfile.TemporaryDirectory(
        prefix="knowledge_pg_sync_"
    ) as directory:

        test_root = Path(directory)
        test_folder = (
            test_root / "database" / "project_knowledge"
        )
        test_folder.mkdir(parents=True)

        for name in (
            "detect_source_changes.py",
            "prepare_source_sync.py",
        ):
            shutil.copy2(FOLDER / name, test_folder / name)

        core = test_root / "core"
        core.mkdir()

        (core / "example.py").write_bytes(NEW_CONTENT)
        (core / "new_module.py").write_bytes(ADDED_CONTENT)

        baseline = {
            "project_key": "dubai-real-estate-ai",
            "source_count": 1,
            "files": [
                {
                    "source_path": "core/example.py",
                    "sha256": fingerprint(OLD_CONTENT),
                    "size_bytes": len(OLD_CONTENT),
                }
            ],
        }

        (
            test_folder / "source_versions_baseline.json"
        ).write_text(
            json.dumps(baseline),
            encoding="utf-8",
        )

        run_tool(
            test_folder / "detect_source_changes.py"
        )

        report = json.loads(
            (test_folder / "source_change_report.json")
            .read_text(encoding="utf-8")
        )

        assert report["summary"] == {
            "added": 1,
            "modified": 1,
            "unchanged": 0,
            "missing": 0,
        }

        run_tool(
            test_folder / "prepare_source_sync.py"
        )

        source_sql = (
            test_folder / "008_incremental_source_sync.sql"
        )

        if not source_sql.is_file():
            raise RuntimeError("Synchronization SQL missing")

        sql = source_sql.read_text(encoding="utf-8")

        for expected in (
            fingerprint(OLD_CONTENT),
            fingerprint(NEW_CONTENT),
            fingerprint(ADDED_CONTENT),
            "core/example.py",
            "core/new_module.py",
        ):
            if expected not in sql:
                raise RuntimeError(
                    "Expected test evidence missing from SQL"
                )

        shutil.copy2(source_sql, DESTINATION)

    print("PASS: Synthetic PostgreSQL SQL prepared")
    print("Original hash:", fingerprint(OLD_CONTENT))
    print("Modified hash:", fingerprint(NEW_CONTENT))
    print("Added hash:", fingerprint(ADDED_CONTENT))
    print("Output:", DESTINATION)
    print("No PostgreSQL writes performed")


if __name__ == "__main__":
    main()
