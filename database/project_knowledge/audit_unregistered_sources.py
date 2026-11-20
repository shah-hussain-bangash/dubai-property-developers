"""Step 361: read-only audit of Git-visible files absent from source registry."""

import csv
import io
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = "dubai_ai_knowledge_verify_20261019_095633"

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "node_modules",
    "__pycache__", ".next", ".pytest_cache",
    "dist", "build"
}

EXCLUDED_SUFFIXES = {
    ".pyc", ".pyo", ".log", ".dump", ".db", ".sqlite",
    ".sqlite3", ".zip", ".tar", ".gz", ".bak"
}


def run(command):
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        timeout=90,
        check=False,
    )

    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(message or "Command failed")

    return result.stdout


def registered_paths():
    sql = """
    COPY (
        SELECT source_path
        FROM project_knowledge.source_versions
        WHERE project_id = (
            SELECT id
            FROM project_knowledge.projects
            WHERE project_key = 'dubai-real-estate-ai'
        )
        ORDER BY source_path
    ) TO STDOUT WITH (FORMAT CSV);
    """

    output = run([
        "docker", "compose", "exec", "-T", "postgres",
        "psql", "-U", "dubai_ai", "-d", DB,
        "-X", "-q", "-v", "ON_ERROR_STOP=1", "-c", sql,
    ])

    rows = csv.reader(io.StringIO(output.decode("utf-8-sig")))
    paths = {
        row[0].replace("\\", "/")
        for row in rows if row
    }

    if len(paths) != 325:
        raise RuntimeError(
            f"Unexpected registered source count: {len(paths)}"
        )

    return paths


def git_visible_paths():
    # Includes tracked files and non-ignored untracked files.
    output = run([
        "git", "ls-files", "--cached", "--others",
        "--exclude-standard", "-z"
    ])

    return {
        path.decode("utf-8", errors="replace").replace("\\", "/")
        for path in output.split(b"\0") if path
    }


def classification(path):
    suffix = Path(path).suffix.lower()

    if suffix in {
        ".py", ".js", ".jsx", ".ts", ".tsx",
        ".sql", ".json", ".yaml", ".yml", ".toml"
    }:
        return "code_or_configuration"

    if suffix in {".md", ".txt", ".rst"}:
        return "documentation"

    return "other"


def main():
    registry = registered_paths()
    candidates = git_visible_paths()

    results = []

    for path in sorted(candidates - registry):
        parts = Path(path).parts

        if any(part in EXCLUDED_DIRS for part in parts):
            continue

        target = ROOT / path

        if not target.is_file() or target.is_symlink():
            continue

        if target.suffix.lower() in EXCLUDED_SUFFIXES:
            continue

        if target.name.startswith(".env"):
            continue

        results.append({
            "source_path": path,
            "category": classification(path),
            "size_bytes": target.stat().st_size,
        })

    counts = Counter(row["category"] for row in results)

    report_dir = ROOT / "database" / "project_knowledge" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = report_dir / f"step361_unregistered_sources_{stamp}.csv"

    with report.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["source_path", "category", "size_bytes"],
        )
        writer.writeheader()
        writer.writerows(results)

    print("PASS: Registered baseline:", len(registry))
    print("Git-visible paths:", len(candidates))
    print("Unregistered file candidates:", len(results))

    for category in (
        "code_or_configuration",
        "documentation",
        "other",
    ):
        print(f"{category}: {counts[category]}")

    print("\nFirst 30 candidates:")

    for row in results[:30]:
        print(row["category"], row["source_path"])

    print("\nReport:", report)
    print("PASS: Step 361 read-only audit completed")


if __name__ == "__main__":
    main()
