"""Build guarded, rollback-only seventh-batch registration SQL."""

import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PK = ROOT / "database/project_knowledge"
REPORTS = PK / "reports"

MANIFEST = REPORTS / "step396_registration_batch7.csv"
REVIEW = REPORTS / "step397_safety_review.csv"
TEMPLATE = PK / "032_test_registration_batch6.sql"
OUTPUT = PK / "034_test_registration_batch7.sql"

DB = "dubai_ai_knowledge_verify_20261019_095633"
EXPECTED_TYPES = {".py": 3, ".yml": 3, ".md": 4}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError("Step 398 SQL already exists. Stop.")

    batch = read_csv(MANIFEST)
    reviews = read_csv(REVIEW)

    if len(batch) != 10 or len(reviews) != 10:
        raise RuntimeError("Expected ten manifest and review rows.")

    review_map = {r["source_path"]: r for r in reviews}

    if len(review_map) != 10:
        raise RuntimeError("Duplicate review paths.")

    seen = set()
    counts = {key: 0 for key in EXPECTED_TYPES}
    priorities = {"P1": 0, "P2": 0}
    values = []

    for item in batch:
        path = item["source_path"]
        sha = item["sha256"]

        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
            raise RuntimeError(f"Unsafe path: {path}")

        if any(p in ("", ".", "..") for p in path.split("/")):
            raise RuntimeError(f"Unsafe path component: {path}")

        if path in seen:
            raise RuntimeError(f"Duplicate path: {path}")

        seen.add(path)

        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise RuntimeError(f"Invalid hash: {path}")

        suffix = Path(path).suffix.lower()

        if suffix not in EXPECTED_TYPES:
            raise RuntimeError(f"Unexpected file type: {path}")

        counts[suffix] += 1

        priority = item["priority"]

        if priority not in priorities:
            raise RuntimeError(f"Unexpected priority: {path}")

        priorities[priority] += 1

        if any(
            [
                item["file_type"] != suffix,
                item["registration_mode"] != "metadata_only",
                item["execute_source"] != "false",
                item["status"] != "pending_safety_review",
                item["approved_for_live_registration"] != "false",
            ]
        ):
            raise RuntimeError(f"Manifest status mismatch: {path}")

        review = review_map.get(path)

        expected_review = {
            "priority": priority,
            "file_type": suffix,
            "sha256_verified": "true",
            "size_verified": "true",
            "registration_mode": "metadata_only",
            "execute_source": "false",
            "approved_for_live_registration": "false",
            "review_status": "fingerprint_and_type_verified",
        }

        if review is None or any(review.get(k) != v for k, v in expected_review.items()):
            raise RuntimeError(f"Safety review mismatch: {path}")

        current = ROOT

        for part in path.split("/"):
            current = current / part
            if current.is_symlink():
                raise RuntimeError(f"Symlink detected: {path}")

        current.resolve(strict=True).relative_to(ROOT.resolve())

        if not current.is_file():
            raise RuntimeError(f"Missing file: {path}")

        content = current.read_bytes()

        if hashlib.sha256(content).hexdigest() != sha:
            raise RuntimeError(f"Changed fingerprint: {path}")

        if len(content) != int(item["size_bytes"]):
            raise RuntimeError(f"File size changed: {path}")

        values.append(f"('{path}', '{sha}', {len(content)})")

    if counts != EXPECTED_TYPES:
        raise RuntimeError(f"Unexpected type distribution: {counts}")

    if priorities != {"P1": 3, "P2": 7}:
        raise RuntimeError(f"Unexpected priorities: {priorities}")

    sql = TEMPLATE.read_text(encoding="utf-8-sig")

    if f"current_database() <> '{DB}'" not in sql:
        raise RuntimeError("Database guard missing.")

    if not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I):
        raise RuntimeError("Template does not end with ROLLBACK.")

    if re.search(r"\bCOMMIT\s*;", sql, re.I):
        raise RuntimeError("COMMIT is not permitted.")

    match = re.search(
        r"INSERT INTO step392_batch VALUES\s+(.+?);",
        sql,
        re.S,
    )

    if match is None:
        raise RuntimeError("Template VALUES clause missing.")

    sql = sql[: match.start(1)] + ",\n".join(values) + sql[match.end(1) :]

    if (
        len(re.findall(r"<> 375\b", sql)) != 4
        or len(re.findall(r"<> 385\b", sql)) != 4
        or len(re.findall(r"\) <> 60\b", sql)) != 1
    ):
        raise RuntimeError("Unexpected template count guards.")

    # Advance from the sixth-batch baseline to seventh-batch totals.
    sql = re.sub(r"<> 385\b", "<> __NEW_TOTAL__", sql)
    sql = re.sub(r"<> 375\b", "<> 385", sql)
    sql = sql.replace("<> __NEW_TOTAL__", "<> 395")
    sql = re.sub(r"\) <> 60\b", ") <> 70", sql)

    sql = sql.replace("step392_batch", "step398_batch")
    sql = sql.replace("sixth-batch", "seventh-batch")
    sql = sql.replace("Step 392", "Step 398")

    if (
        len(re.findall(r"<> 385\b", sql)) != 4
        or len(re.findall(r"<> 395\b", sql)) != 4
        or len(re.findall(r"\) <> 70\b", sql)) != 1
        or "step392_batch" in sql
        or "__NEW_TOTAL__" in sql
        or len(re.findall(r"\bROLLBACK\s*;", sql, re.I)) != 1
        or re.search(r"\bCOMMIT\s*;", sql, re.I)
        or "All ten seventh-batch registrations validated" not in sql
    ):
        raise RuntimeError("Generated SQL validation failed.")

    OUTPUT.write_text(sql, encoding="utf-8")

    print("PASS: Ten seventh-batch files rehashed.")
    print("PASS: Step 397 safety review reconciled.")
    print("PASS: Three P1 and seven P2 registrations verified.")
    print("PASS: Baseline 385 and temporary total 395 validated.")
    print("PASS: Expected added-event total 70 validated.")
    print("PASS: Rollback-only SQL generated.")
    print("SQL:", OUTPUT)


if __name__ == "__main__":
    main()
