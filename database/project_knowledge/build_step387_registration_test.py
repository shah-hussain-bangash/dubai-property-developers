"""Generate a guarded rollback-only fifth-batch registration test."""

import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "database/project_knowledge/reports"

MANIFEST = REPORTS / "step385_registration_batch5.csv"
REVIEW = REPORTS / "step386_safety_review.csv"
TEMPLATE = ROOT / "database/project_knowledge/024_test_registration_batch2.sql"
OUTPUT = ROOT / "database/project_knowledge/030_test_registration_batch5.sql"

DB = "dubai_ai_knowledge_verify_20261019_095633"

EXPECTED_EXTENSIONS = {
    ".css": 2,
    ".json": 1,
    ".py": 2,
    ".sql": 5,
}


def load_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    if OUTPUT.exists():
        raise RuntimeError("Step 387 SQL already exists. Stop.")

    batch = load_csv(MANIFEST)
    reviews = load_csv(REVIEW)

    if len(batch) != 10 or len(reviews) != 10:
        raise RuntimeError("Expected ten batch and ten review records.")

    review_by_path = {r["source_path"]: r for r in reviews}

    if len(review_by_path) != 10:
        raise RuntimeError("Duplicate safety-review paths.")

    if len({r["source_path"] for r in batch}) != 10:
        raise RuntimeError("Duplicate batch paths.")

    extension_counts = {key: 0 for key in EXPECTED_EXTENSIONS}
    values = []

    for row in batch:
        path = row["source_path"]
        sha = row["sha256"]

        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
            raise RuntimeError(f"Unsafe path: {path}")

        if any(part in ("", ".", "..") for part in path.split("/")):
            raise RuntimeError(f"Unsafe path component: {path}")

        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise RuntimeError(f"Invalid SHA-256: {path}")

        if (
            row["priority"] != "P1"
            or row["status"] != "ready_for_isolated_test"
            or row["approved_for_live_registration"] != "false"
        ):
            raise RuntimeError(f"Unapproved manifest entry: {path}")

        extension = Path(path).suffix.lower()

        if extension not in EXPECTED_EXTENSIONS:
            raise RuntimeError(f"Unexpected extension: {path}")

        extension_counts[extension] += 1

        review = review_by_path.get(path)

        if review is None:
            raise RuntimeError(f"Missing safety review: {path}")

        if (
            review["sha256_verified"] != "true"
            or review["size_verified"] != "true"
            or review["registration_mode"] != "metadata_only"
            or review["execute_source"] != "false"
            or review["approved_for_live_registration"] != "false"
            or review["review_status"] != "fingerprint_and_type_verified"
        ):
            raise RuntimeError(f"Invalid safety-review status: {path}")

        current = ROOT

        for component in path.split("/"):
            current = current / component

            if current.is_symlink():
                raise RuntimeError(f"Symlink rejected: {path}")

        current.resolve(strict=True).relative_to(ROOT.resolve())

        if not current.is_file():
            raise RuntimeError(f"Missing source file: {path}")

        content = current.read_bytes()

        if hashlib.sha256(content).hexdigest() != sha:
            raise RuntimeError(f"Fingerprint mismatch: {path}")

        if len(content) != int(row["size_bytes"]):
            raise RuntimeError(f"File-size mismatch: {path}")

        values.append(f"('{path}', '{sha}', {len(content)})")

    if extension_counts != EXPECTED_EXTENSIONS:
        raise RuntimeError(f"Unexpected file types: {extension_counts}")

    sql = TEMPLATE.read_text(encoding="utf-8-sig")

    if f"current_database() <> '{DB}'" not in sql:
        raise RuntimeError("Verification database guard missing.")

    if not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I):
        raise RuntimeError("Template must end with ROLLBACK.")

    if re.search(r"\bCOMMIT\s*;", sql, re.I):
        raise RuntimeError("COMMIT prohibited in test SQL.")

    match = re.search(
        r"INSERT INTO step373_batch VALUES\s+(.+?);",
        sql,
        re.S,
    )

    if match is None:
        raise RuntimeError("Expected source VALUES section missing.")

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
        raise RuntimeError("Unexpected template count checks.")

    # Original template: 335 -> 345.
    # Fifth-batch test: 365 -> 375.
    sql = sql.replace("<> 345", "<> 375")
    sql = sql.replace("<> 335", "<> 365")
    sql = sql.replace(") <> 20", ") <> 50")

    sql = sql.replace("step373_batch", "step387_batch")
    sql = sql.replace(
        "Step 373 rollback-only test",
        "Step 387 rollback-only test",
    )
    sql = sql.replace(
        "All ten second-batch registrations validated",
        "All ten fifth-batch registrations validated",
    )

    if (
        sql.count("<> 365") != 4
        or sql.count("<> 375") != 4
        or sql.count(") <> 50") != 1
        or "step373_batch" in sql
        or len(re.findall(r"\bROLLBACK\s*;", sql, re.I)) != 1
        or re.search(r"\bCOMMIT\s*;", sql, re.I)
    ):
        raise RuntimeError("Generated SQL failed safety checks.")

    OUTPUT.write_text(sql, encoding="utf-8")

    print("PASS: All ten source files rehashed.")
    print("PASS: Step 386 safety review reconciled.")
    print("PASS: Baseline 365 and temporary total 375 validated.")
    print("PASS: Added-event total 50 validated.")
    print("PASS: Rollback-only SQL generated.")
    print("SQL:", OUTPUT)


if __name__ == "__main__":
    main()
