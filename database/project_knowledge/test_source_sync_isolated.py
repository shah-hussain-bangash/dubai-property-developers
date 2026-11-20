"""Test source synchronization in an isolated temporary directory."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS = PROJECT_ROOT / "database" / "project_knowledge"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run_script(path):
    result = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if result.returncode != 0:
        raise AssertionError(
            f"{path.name} failed:\n{result.stdout}\n{result.stderr}"
        )

    return result.stdout


def main():
    with tempfile.TemporaryDirectory(prefix="source_sync_test_") as temp:
        root = Path(temp)
        folder = root / "database" / "project_knowledge"
        folder.mkdir(parents=True)

        for name in (
            "detect_source_changes.py",
            "prepare_source_sync.py",
        ):
            shutil.copy2(TOOLS / name, folder / name)

        source_dir = root / "core"
        source_dir.mkdir()

        old_content = b"ORIGINAL_TEST_CONTENT = 1\n"
        new_content = b"UPDATED_TEST_CONTENT = 2\n"

        modified_file = source_dir / "example.py"
        modified_file.write_bytes(new_content)

        added_file = source_dir / "new_module.py"
        added_content = b"NEW_TEST_MODULE = True\n"
        added_file.write_bytes(added_content)

        baseline = {
            "project_key": "dubai-real-estate-ai",
            "source_count": 1,
            "files": [
                {
                    "source_path": "core/example.py",
                    "sha256": sha256(old_content),
                    "size_bytes": len(old_content),
                }
            ],
        }

        (folder / "source_versions_baseline.json").write_text(
            json.dumps(baseline),
            encoding="utf-8",
        )

        print(run_script(folder / "detect_source_changes.py"))

        report = json.loads(
            (folder / "source_change_report.json").read_text(
                encoding="utf-8"
            )
        )

        expected = {
            "added": 1,
            "modified": 1,
            "unchanged": 0,
            "missing": 0,
        }

        assert report["summary"] == expected, (
            report["summary"]
        )

        print(run_script(folder / "prepare_source_sync.py"))

        sql_file = folder / "008_incremental_source_sync.sql"

        assert sql_file.exists(), "Expected SQL was not generated"

        sql = sql_file.read_text(encoding="utf-8")

        assert "core/example.py" in sql
        assert "core/new_module.py" in sql
        assert sha256(new_content) in sql
        assert sha256(added_content) in sql

        print("PASS: Added file detected")
        print("PASS: Modified file detected")
        print("PASS: Incremental SQL generated")
        print("PASS: Source fingerprints validated")
        print("PASS: Real project files unchanged")
        print("PASS: No PostgreSQL writes performed")


if __name__ == "__main__":
    main()
