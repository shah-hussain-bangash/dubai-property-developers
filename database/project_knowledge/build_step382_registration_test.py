"""Generate and validate fourth-batch rollback-only SQL."""

import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "database/project_knowledge/reports"
MANIFEST = REPORTS / "step381_registration_batch4.csv"
INVENTORY = REPORTS / "step380_remaining_inventory.csv"
TEMPLATE = ROOT / "database/project_knowledge/024_test_registration_batch2.sql"
OUTPUT = ROOT / "database/project_knowledge/028_test_registration_batch4.sql"
DB = "dubai_ai_knowledge_verify_20261019_095633"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main():
    if OUTPUT.exists():
        raise RuntimeError("Step 382 SQL already exists. Stop.")

    rows = read_csv(MANIFEST)
    inventory = read_csv(INVENTORY)

    eligible = sorted(
        (
            r for r in inventory
            if r["priority"] == "P1"
            and r["inventory_status"] == "pending_test_registration"
            and r["validation_status"] == "preliminary_scan_clear"
            and r["registration_approved"] == "false"
        ),
        key=lambda r: r["source_path"],
    )

    expected = eligible[:10]

    if len(eligible) != 33 or len(rows) != 10:
        raise RuntimeError("Unexpected P1 inventory or batch size.")

    if [r["source_path"] for r in rows] != [
        r["source_path"] for r in expected
    ]:
        raise RuntimeError("Batch differs from selected P1 files.")

    values = []

    for row, original in zip(rows, expected):
        path = row["source_path"]
        sha = row["sha256"]

        if not re.fullmatch(
            r"apps/dashboard/[A-Za-z0-9_./-]+\.css", path
        ):
            raise RuntimeError(f"Unexpected dashboard CSS path: {path}")

        if any(p in ("", ".", "..") for p in path.split("/")):
            raise RuntimeError(f"Unsafe path: {path}")

        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise RuntimeError(f"Invalid SHA-256: {path}")

        if (
            row["priority"] != "P1"
            or row["status"] != "ready_for_isolated_test"
            or row["approved_for_live_registration"] != "false"
            or original["sha256"] != sha
        ):
            raise RuntimeError(f"Manifest/inventory mismatch: {path}")

        current = ROOT

        for component in path.split("/"):
            current = current / component
            if current.is_symlink():
                raise RuntimeError(f"Symlink rejected: {path}")

        current.resolve(strict=True).relative_to(ROOT.resolve())

        if not current.is_file():
            raise RuntimeError(f"File missing: {path}")

        content = current.read_bytes()

        if hashlib.sha256(content).hexdigest() != sha:
            raise RuntimeError(f"Fingerprint changed: {path}")

        if len(content) != int(row["size_bytes"]):
            raise RuntimeError(f"File size changed: {path}")

        values.append(f"('{path}', '{sha}', {len(content)})")

    sql = TEMPLATE.read_text(encoding="utf-8-sig")

    if (
        f"current_database() <> '{DB}'" not in sql
        or not re.search(r"\bROLLBACK;\s*$", sql, re.I)
        or re.search(r"\bCOMMIT\s*;", sql, re.I)
    ):
        raise RuntimeError("Unsafe SQL template.")

    pattern = r"INSERT INTO step373_batch VALUES\s+(.+?);"
    match = re.search(pattern, sql, re.S)

    if match is None:
        raise RuntimeError("Template batch VALUES missing.")

    sql = (
        sql[:match.start(1)]
        + ",\n".join(values)
        + sql[match.end(1):]
    )

    if (
        sql.count("<> 335") != 4
        or sql.count("<> 345") != 4
        or sql.count(") <> 20") != 1
    ):
        raise RuntimeError("Unexpected template baseline checks.")

    # Replace in this order to avoid accidentally changing new values.
    sql = sql.replace("<> 345", "<> 365")
    sql = sql.replace("<> 335", "<> 355")
    sql = sql.replace(") <> 20", ") <> 40")

    sql = sql.replace("step373_batch", "step382_batch")
    sql = sql.replace(
        "Step 373 rollback-only test",
        "Step 382 rollback-only test"
    )
    sql = sql.replace(
        "Step 373 baseline",
        "Step 382 baseline"
    )
    sql = sql.replace(
        "All ten second-batch registrations validated",
        "All ten fourth-batch registrations validated"
    )

    if (
        sql.count("<> 355") != 4
        or sql.count("<> 365") != 4
        or sql.count(") <> 40") != 1
        or sql.count("ROLLBACK;") != 1
        or "COMMIT;" in sql
        or "step373_batch" in sql
    ):
        raise RuntimeError("Generated rollback SQL failed validation.")

    OUTPUT.write_text(sql, encoding="utf-8")

    print("PASS: Ten dashboard CSS files rehashed.")
    print("PASS: SQL baseline 355 and test total 365 validated.")
    print("PASS: Expected added-event count 40 verified.")
    print("PASS: Rollback-only SQL generated.")
    print("SQL:", OUTPUT)


if __name__ == "__main__":
    main()
