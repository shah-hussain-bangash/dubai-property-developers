"""Build rollback-only SQL for six ninth-batch metadata records."""

import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PK = ROOT / "database/project_knowledge"
REPORTS = PK / "reports"

MANIFEST = REPORTS / "step408_registration_batch9.csv"
REVIEW = REPORTS / "step409_safety_review.csv"
TEMPLATE = PK / "036_test_registration_batch8.sql"
OUTPUT = PK / "038_test_registration_batch9.sql"

DB = "dubai_ai_knowledge_verify_20261019_095633"

EXPECTED_PATHS = {
    "docs/development/integrations.md",
    "docs/development/roadmap.md",
    "docs/development/windows-setup.md",
    "docs/recovery-ownership-protocol.md",
    "docs/security/README.md",
    "README.md",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError("Step 410 SQL already exists. Stop.")

    batch = read_csv(MANIFEST)
    reviews = read_csv(REVIEW)

    if len(batch) != 6 or len(reviews) != 6:
        raise RuntimeError("Expected six manifest and review rows.")

    if {r["source_path"] for r in batch} != EXPECTED_PATHS:
        raise RuntimeError("Unexpected ninth-batch source paths.")

    review_map = {r["source_path"]: r for r in reviews}

    if len(review_map) != 6:
        raise RuntimeError("Duplicate safety-review paths.")

    values = []
    seen = set()

    for row in batch:
        path = row["source_path"]
        sha = row["sha256"]

        if path in seen:
            raise RuntimeError(f"Duplicate path: {path}")
        seen.add(path)

        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
            raise RuntimeError(f"Unsafe path: {path}")

        if any(p in ("", ".", "..") for p in path.split("/")):
            raise RuntimeError(f"Unsafe path component: {path}")

        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise RuntimeError(f"Invalid SHA-256: {path}")

        if not re.fullmatch(r"[0-9]+", row["size_bytes"]):
            raise RuntimeError(f"Invalid file size: {path}")

        required = {
            "priority": "P2",
            "file_type": ".md",
            "registration_mode": "metadata_only",
            "execute_source": "false",
            "status": "pending_safety_review",
            "approved_for_live_registration": "false",
        }

        if any(row.get(k) != v for k, v in required.items()):
            raise RuntimeError(f"Manifest status mismatch: {path}")

        review = review_map.get(path)

        required_review = {
            "priority": "P2",
            "file_type": ".md",
            "sha256_verified": "true",
            "size_verified": "true",
            "registration_mode": "metadata_only",
            "execute_source": "false",
            "approved_for_live_registration": "false",
            "review_status": "fingerprint_and_type_verified",
        }

        if review is None or any(review.get(k) != v for k, v in required_review.items()):
            raise RuntimeError(f"Safety review mismatch: {path}")

        current = ROOT

        for part in path.split("/"):
            current = current / part
            if current.is_symlink():
                raise RuntimeError(f"Symlink rejected: {path}")

        current.resolve(strict=True).relative_to(ROOT.resolve())

        if not current.is_file():
            raise RuntimeError(f"Source missing: {path}")

        contents = current.read_bytes()

        if hashlib.sha256(contents).hexdigest() != sha:
            raise RuntimeError(f"Fingerprint mismatch: {path}")

        if len(contents) != int(row["size_bytes"]):
            raise RuntimeError(f"Size mismatch: {path}")

        values.append(f"('{path}', '{sha}', {len(contents)})")

    sql = TEMPLATE.read_text(encoding="utf-8-sig")

    if f"current_database() <> '{DB}'" not in sql:
        raise RuntimeError("Wrong verification database guard.")

    if not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I):
        raise RuntimeError("Template must end with ROLLBACK.")

    if re.search(r"\bCOMMIT\s*;", sql, re.I):
        raise RuntimeError("COMMIT prohibited.")

    match = re.search(
        r"INSERT INTO step404_batch VALUES\s+(.+?);",
        sql,
        re.S,
    )

    if match is None:
        raise RuntimeError("Step 404 values clause missing.")

    sql = sql[: match.start(1)] + ",\n".join(values) + sql[match.end(1) :]

    if (
        len(re.findall(r"<> 395\b", sql)) != 4
        or len(re.findall(r"<> 405\b", sql)) != 4
        or len(re.findall(r"\) <> 80\b", sql)) != 1
    ):
        raise RuntimeError("Unexpected template guards.")

    # Eighth batch: 395 -> 405 and 70 -> 80.
    # Ninth batch: 405 -> 411 and 80 -> 86.
    sql = re.sub(r"<> 405\b", "<> __NEW_TOTAL__", sql)
    sql = re.sub(r"<> 395\b", "<> 405", sql)
    sql = sql.replace("<> __NEW_TOTAL__", "<> 411")
    sql = re.sub(r"\) <> 80\b", ") <> 86", sql)

    sql = sql.replace("step404_batch", "step410_batch")
    sql = sql.replace("eighth-batch", "ninth-batch")
    sql = sql.replace("Step 404", "Step 410")

    if (
        len(re.findall(r"<> 405\b", sql)) != 4
        or len(re.findall(r"<> 411\b", sql)) != 4
        or len(re.findall(r"\) <> 86\b", sql)) != 1
        or "step404_batch" in sql
        or "__NEW_TOTAL__" in sql
        or "All ten ninth-batch" not in sql
        or len(re.findall(r"\bROLLBACK\s*;", sql, re.I)) != 1
        or re.search(r"\bCOMMIT\s*;", sql, re.I)
    ):
        raise RuntimeError("Generated SQL validation failed.")

    # The template notices are descriptive, not functional checks.
    sql = sql.replace(
        "All ten ninth-batch registrations validated",
        "All six ninth-batch registrations validated",
    )

    if "All six ninth-batch registrations validated" not in sql:
        raise RuntimeError("Ninth-batch integrity notice missing.")

    if "Four-table integrity and history verified" not in sql:
        raise RuntimeError("Integrity notice missing.")

    OUTPUT.write_text(sql, encoding="utf-8")

    print("PASS: All six P2 Markdown files rehashed.")
    print("PASS: Step 409 safety review reconciled.")
    print("PASS: Baseline 405 and temporary total 411 validated.")
    print("PASS: Expected added-event total 86 validated.")
    print("PASS: Rollback-only SQL generated.")
    print("SQL:", OUTPUT)


if __name__ == "__main__":
    main()
