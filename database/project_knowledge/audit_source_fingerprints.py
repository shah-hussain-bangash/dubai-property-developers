"""Step 360: read-only comparison of PostgreSQL source hashes and local files."""

import csv
import hashlib
import io
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
RESTORE_DB = "dubai_ai_knowledge_verify_20261019_095633"
EXPECTED_COUNT = 325


def fetch_registered_sources():
    sql = """
    COPY (
        SELECT source_path, content_sha256
        FROM project_knowledge.source_versions
        WHERE project_id = (
            SELECT id
            FROM project_knowledge.projects
            WHERE project_key = 'dubai-real-estate-ai'
        )
        ORDER BY source_path
    ) TO STDOUT WITH (FORMAT CSV, HEADER TRUE);
    """

    command = [
        "docker", "compose", "exec", "-T", "postgres",
        "psql", "-U", "dubai_ai", "-d", RESTORE_DB,
        "-X", "-q", "-v", "ON_ERROR_STOP=1", "-c", sql,
    ]

    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)

    records = list(csv.DictReader(io.StringIO(result.stdout)))

    if len(records) != EXPECTED_COUNT:
        raise RuntimeError(
            f"Unexpected source count: {len(records)}"
        )

    paths = [row["source_path"] for row in records]

    if len(set(paths)) != len(paths):
        raise RuntimeError("Duplicate source paths found")

    return records


def inspect_file(row):
    original_path = row["source_path"]
    expected_hash = row["content_sha256"]

    result = {
        "source_path": original_path,
        "database_sha256": expected_hash,
        "local_sha256": "",
        "status": "",
    }

    normalized = original_path.replace("\\", "/")
    path = PurePosixPath(normalized)

    if (
        not normalized
        or normalized.startswith("/")
        or ":" in normalized
        or any(part in ("", ".", "..") for part in normalized.split("/"))
    ):
        result["status"] = "unsafe_path"
        return result

    target = ROOT.joinpath(*path.parts)

    try:
        # Resolve the destination and block paths outside this project.
        resolved = target.resolve(strict=False)
        resolved.relative_to(ROOT.resolve())

        if not target.exists():
            result["status"] = "missing"
            return result

        if not target.is_file():
            result["status"] = "not_regular_file"
            return result

        # Avoid reading files through symbolic links.
        if target.is_symlink() or target.resolve() != target.absolute():
            result["status"] = "unsafe_path"
            return result

        digest = hashlib.sha256()

        with target.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)

        actual_hash = digest.hexdigest()
        result["local_sha256"] = actual_hash
        result["status"] = (
            "match" if actual_hash == expected_hash else "changed"
        )

    except (OSError, ValueError):
        result["status"] = "inspection_error"

    return result


def main():
    records = fetch_registered_sources()

    print("PASS: Retrieved 325 source fingerprints from restored database")

    results = [inspect_file(row) for row in records]
    counts = Counter(row["status"] for row in results)

    report_dir = ROOT / "database" / "project_knowledge" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"step360_fingerprint_audit_{stamp}.csv"

    if report_file.exists():
        raise RuntimeError("Report already exists")

    with report_file.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "source_path",
                "database_sha256",
                "local_sha256",
                "status",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    print("\nStep 360 fingerprint audit")
    print("Registered files:", len(records))

    for status in (
        "match",
        "changed",
        "missing",
        "unsafe_path",
        "not_regular_file",
        "inspection_error",
    ):
        print(f"{status}: {counts[status]}")

    print("\nReport:", report_file)

    exceptions = [row for row in results if row["status"] != "match"]

    if exceptions:
        print("\nFirst 20 differences:")
        for row in exceptions[:20]:
            print(f"{row['status']}: {row['source_path']}")
    else:
        print("PASS: All registered fingerprints match local files")

    print("\nPASS: Read-only audit completed")


if __name__ == "__main__":
    main()
