"""Build a guarded rollback-only sixth-batch registration test."""

import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "database/project_knowledge/reports"

MANIFEST = REPORTS / "step390_registration_batch6.csv"
REVIEW = REPORTS / "step391_safety_review.csv"
TEMPLATE = ROOT / "database/project_knowledge/030_test_registration_batch5.sql"
OUTPUT = ROOT / "database/project_knowledge/032_test_registration_batch6.sql"

DB = "dubai_ai_knowledge_verify_20261019_095633"


def load_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    if OUTPUT.exists():
        raise RuntimeError("Step 392 SQL already exists. Stop.")

    batch = load_csv(MANIFEST)
    reviews = load_csv(REVIEW)

    if len(batch) != 10 or len(reviews) != 10:
        raise RuntimeError("Expected ten entries in each report.")

    review_map = {r["source_path"]: r for r in reviews}

    if len(review_map) != 10:
        raise RuntimeError("Duplicate review paths.")

    paths = set()
    values = []
    python_count = 0
    sql_count = 0

    for item in batch:
        path = item["source_path"]
        sha = item["sha256"]

        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
            raise RuntimeError(f"Unsafe path: {path}")

        if any(p in ("", ".", "..") for p in path.split("/")):
            raise RuntimeError(f"Unsafe path component: {path}")

        if path in paths:
            raise RuntimeError(f"Duplicate source path: {path}")

        paths.add(path)

        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise RuntimeError(f"Invalid hash: {path}")

        suffix = Path(path).suffix.lower()

        if suffix == ".py":
            expected_type = "python_source"
            python_count += 1
        elif suffix == ".sql":
            expected_type = "sql_source_only"
            sql_count += 1
        else:
            raise RuntimeError(f"Unexpected extension: {path}")

        if (
            item["priority"] != "P1"
            or item["file_type"] != expected_type
            or item["status"] != "ready_for_isolated_test"
            or item["registration_mode"] != "metadata_only"
            or item["execute_source"] != "false"
            or item["approved_for_live_registration"] != "false"
        ):
            raise RuntimeError(f"Invalid manifest status: {path}")

        review = review_map.get(path)

        if review is None or any(
            review.get(field) != value
            for field, value in {
                "file_type": expected_type,
                "sha256_verified": "true",
                "size_verified": "true",
                "registration_mode": "metadata_only",
                "execute_source": "false",
                "approved_for_live_registration": "false",
                "review_status": "fingerprint_and_type_verified",
            }.items()
        ):
            raise RuntimeError(f"Safety review mismatch: {path}")

        current = ROOT

        for part in path.split("/"):
            current = current / part

            if current.is_symlink():
                raise RuntimeError(f"Symlink rejected: {path}")

        current.resolve(strict=True).relative_to(ROOT.resolve())

        if not current.is_file():
            raise RuntimeError(f"Missing source file: {path}")

        content = current.read_bytes()

        if hashlib.sha256(content).hexdigest() != sha:
            raise RuntimeError(f"Changed fingerprint: {path}")

        if len(content) != int(item["size_bytes"]):
            raise RuntimeError(f"Changed file size: {path}")

        values.append(f"('{path}', '{sha}', {len(content)})")

    if python_count != 7 or sql_count != 3:
        raise RuntimeError("Unexpected Python/SQL distribution.")

    sql = TEMPLATE.read_text(encoding="utf-8-sig")

    if f"current_database() <> '{DB}'" not in sql:
        raise RuntimeError("Verification database guard missing.")

    if not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I):
        raise RuntimeError("Template must end with ROLLBACK.")

    if re.search(r"\bCOMMIT\s*;", sql, re.I):
        raise RuntimeError("COMMIT is prohibited.")

    match = re.search(
        r"INSERT INTO step387_batch VALUES\s+(.+?);",
        sql,
        re.S,
    )

    if match is None:
        raise RuntimeError("Fifth-batch VALUES section missing.")

    sql = sql[: match.start(1)] + ",\n".join(values) + sql[match.end(1) :]

    if (
        len(re.findall(r"<> 365\b", sql)) != 4
        or len(re.findall(r"<> 375\b", sql)) != 4
        or len(re.findall(r"\) <> 50\b", sql)) != 1
    ):
        raise RuntimeError("Unexpected template count checks.")

    # Preserve the distinction between old baseline and old total.
    sql = re.sub(r"<> 375\b", "<> __NEW_TOTAL__", sql)
    sql = re.sub(r"<> 365\b", "<> 375", sql)
    sql = sql.replace("<> __NEW_TOTAL__", "<> 385")
    sql = re.sub(r"\) <> 50\b", ") <> 60", sql)

    sql = sql.replace("step387_batch", "step392_batch")
    sql = sql.replace("fifth-batch", "sixth-batch")
    sql = sql.replace("Step 387", "Step 392")

    if (
        len(re.findall(r"<> 375\b", sql)) != 4
        or len(re.findall(r"<> 385\b", sql)) != 4
        or len(re.findall(r"\) <> 60\b", sql)) != 1
        or "step387_batch" in sql
        or "__NEW_TOTAL__" in sql
        or len(re.findall(r"\bROLLBACK\s*;", sql, re.I)) != 1
        or re.search(r"\bCOMMIT\s*;", sql, re.I)
    ):
        raise RuntimeError("Generated SQL failed safety validation.")

    OUTPUT.write_text(sql, encoding="utf-8")

    print("PASS: Ten sixth-batch sources rehashed.")
    print("PASS: Step 391 safety report reconciled.")
    print("PASS: Baseline 375 and temporary total 385 validated.")
    print("PASS: Expected added-event total 60 validated.")
    print("PASS: Rollback-only registration SQL generated.")
    print("SQL:", OUTPUT)


if __name__ == "__main__":
    main()
