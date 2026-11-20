"""Generate third-batch rollback test from validated second-batch SQL."""

import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "database/project_knowledge/reports/step377_registration_batch3.csv"
TEMPLATE = ROOT / "database/project_knowledge/024_test_registration_batch2.sql"
OUTPUT = ROOT / "database/project_knowledge/026_test_registration_batch3.sql"
DB = "dubai_ai_knowledge_verify_20261019_095633"


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError("Step 378 SQL already exists. Stop.")

    with MANIFEST.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    if len(rows) != 10:
        raise RuntimeError("Expected 10 files")

    paths = [row["source_path"] for row in rows]

    if len(set(paths)) != 10:
        raise RuntimeError("Duplicate source paths")

    values = []

    for row in rows:
        path = row["source_path"]
        sha = row["sha256"]

        if not path.startswith("apps/dashboard/"):
            raise RuntimeError(f"Unexpected path: {path}")

        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
            raise RuntimeError(f"Unsafe path: {path}")

        if any(p in ("", ".", "..") for p in path.split("/")):
            raise RuntimeError(f"Invalid path: {path}")

        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise RuntimeError(f"Invalid fingerprint: {path}")

        if (
            row["priority"] != "P1"
            or row["status"] != "ready_for_isolated_test"
            or row["approved_for_live_registration"] != "false"
        ):
            raise RuntimeError(f"Unexpected status: {path}")

        target = ROOT

        for part in path.split("/"):
            target = target / part

            if target.is_symlink():
                raise RuntimeError(f"Symlink rejected: {path}")

        target.resolve(strict=True).relative_to(ROOT.resolve())

        if not target.is_file():
            raise RuntimeError(f"Missing file: {path}")

        content = target.read_bytes()

        if hashlib.sha256(content).hexdigest() != sha:
            raise RuntimeError(f"Fingerprint changed: {path}")

        if len(content) != int(row["size_bytes"]):
            raise RuntimeError(f"File size changed: {path}")

        values.append(f"('{path}', '{sha}', {len(content)})")

    sql = TEMPLATE.read_text(encoding="utf-8-sig")

    if DB not in sql:
        raise RuntimeError("Database target guard missing")

    if not re.search(r"\bROLLBACK;\s*$", sql):
        raise RuntimeError("Template is not rollback-only")

    if re.search(r"\bCOMMIT\s*;", sql, re.IGNORECASE):
        raise RuntimeError("Unexpected COMMIT in template")

    old_values = re.search(
        r"INSERT INTO step373_batch VALUES\s+(.+?);",
        sql,
        re.DOTALL,
    )

    if old_values is None:
        raise RuntimeError("Source VALUES section missing")

    sql = sql[: old_values.start(1)] + ",\n".join(values) + sql[old_values.end(1) :]

    # Update verified baseline and temporary test totals.
    if sql.count("<> 335") != 4:
        raise RuntimeError("Unexpected baseline checks")

    if sql.count("<> 345") != 4:
        raise RuntimeError("Unexpected temporary count checks")

    sql = sql.replace("<> 345", "<> 355")
    sql = sql.replace("<> 335", "<> 345")

    if sql.count(") <> 20") != 1:
        raise RuntimeError("Unexpected added-event count check")

    sql = sql.replace(") <> 20", ") <> 30")

    sql = sql.replace("step373_batch", "step378_batch")
    sql = sql.replace(
        "Step 373 rollback-only test",
        "Step 378 rollback-only test",
    )
    sql = sql.replace("Step 373", "Step 378")

    if "ROLLBACK;" not in sql or "COMMIT;" in sql:
        raise RuntimeError("Rollback-only policy violated")

    OUTPUT.write_text(sql, encoding="utf-8")

    print("PASS: Ten P1 source files rehashed")
    print("PASS: Third-batch SQL generated")
    print("PASS: Rollback-only transaction preserved")
    print("SQL:", OUTPUT)


if __name__ == "__main__":
    main()
