"""Generate metadata-only, rollback-only eighth-batch registration SQL."""

import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PK = ROOT / "database/project_knowledge"
REPORTS = PK / "reports"

MANIFEST = REPORTS / "step402_registration_batch8.csv"
REVIEW = REPORTS / "step403_safety_review.csv"
TEMPLATE = PK / "034_test_registration_batch7.sql"
OUTPUT = PK / "036_test_registration_batch8.sql"

DATABASE = "dubai_ai_knowledge_verify_20261019_095633"
EXPECTED_TYPES = {".yaml": 1, ".yml": 1, ".sql": 1, ".md": 7}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError("Step 404 SQL already exists. Stop.")

    batch = read_csv(MANIFEST)
    reviews = read_csv(REVIEW)

    if len(batch) != 10 or len(reviews) != 10:
        raise RuntimeError("Expected ten manifest and review rows.")

    review_map = {r["source_path"]: r for r in reviews}

    if len(review_map) != 10:
        raise RuntimeError("Duplicate safety-review paths.")

    seen = set()
    counts = {ext: 0 for ext in EXPECTED_TYPES}
    values = []

    for row in batch:
        path = row["source_path"]
        sha = row["sha256"]

        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
            raise RuntimeError(f"Unsafe source path: {path}")

        if any(p in ("", ".", "..") for p in path.split("/")):
            raise RuntimeError(f"Unsafe path component: {path}")

        if path in seen:
            raise RuntimeError(f"Duplicate source path: {path}")

        seen.add(path)

        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise RuntimeError(f"Invalid fingerprint: {path}")

        ext = Path(path).suffix.lower()

        if ext not in EXPECTED_TYPES:
            raise RuntimeError(f"Unsupported source type: {path}")

        counts[ext] += 1

        required = {
            "priority": "P2",
            "file_type": ext,
            "registration_mode": "metadata_only",
            "execute_source": "false",
            "status": "pending_safety_review",
            "approved_for_live_registration": "false",
        }

        if any(row.get(k) != v for k, v in required.items()):
            raise RuntimeError(f"Manifest mismatch: {path}")

        review = review_map.get(path)

        expected_review = {
            "priority": "P2",
            "file_type": ext,
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
                raise RuntimeError(f"Symlink rejected: {path}")

        current.resolve(strict=True).relative_to(ROOT.resolve())

        if not current.is_file():
            raise RuntimeError(f"Missing file: {path}")

        contents = current.read_bytes()

        if hashlib.sha256(contents).hexdigest() != sha:
            raise RuntimeError(f"Fingerprint changed: {path}")

        if len(contents) != int(row["size_bytes"]):
            raise RuntimeError(f"File size changed: {path}")

        values.append(f"('{path}', '{sha}', {len(contents)})")

    if counts != EXPECTED_TYPES:
        raise RuntimeError(f"Unexpected file types: {counts}")

    sql = TEMPLATE.read_text(encoding="utf-8-sig")

    if f"current_database() <> '{DATABASE}'" not in sql:
        raise RuntimeError("Wrong or missing database guard.")

    if not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I):
        raise RuntimeError("Template must end with ROLLBACK.")

    if re.search(r"\bCOMMIT\s*;", sql, re.I):
        raise RuntimeError("COMMIT prohibited.")

    match = re.search(
        r"INSERT INTO step398_batch VALUES\s+(.+?);",
        sql,
        re.S,
    )

    if match is None:
        raise RuntimeError("Template VALUES clause not found.")

    sql = sql[: match.start(1)] + ",\n".join(values) + sql[match.end(1) :]

    if (
        len(re.findall(r"<> 385\b", sql)) != 4
        or len(re.findall(r"<> 395\b", sql)) != 4
        or len(re.findall(r"\) <> 70\b", sql)) != 1
    ):
        raise RuntimeError("Unexpected template count checks.")

    sql = re.sub(r"<> 395\b", "<> __NEW_TOTAL__", sql)
    sql = re.sub(r"<> 385\b", "<> 395", sql)
    sql = sql.replace("<> __NEW_TOTAL__", "<> 405")
    sql = re.sub(r"\) <> 70\b", ") <> 80", sql)

    sql = sql.replace("step398_batch", "step404_batch")
    sql = sql.replace("seventh-batch", "eighth-batch")
    sql = sql.replace("Step 398", "Step 404")

    if (
        len(re.findall(r"<> 395\b", sql)) != 4
        or len(re.findall(r"<> 405\b", sql)) != 4
        or len(re.findall(r"\) <> 80\b", sql)) != 1
        or "step398_batch" in sql
        or "__NEW_TOTAL__" in sql
        or "All ten eighth-batch registrations validated" not in sql
        or len(re.findall(r"\bROLLBACK\s*;", sql, re.I)) != 1
        or re.search(r"\bCOMMIT\s*;", sql, re.I)
    ):
        raise RuntimeError("Generated SQL failed validation.")

    OUTPUT.write_text(sql, encoding="utf-8")

    print("PASS: All ten P2 files rehashed.")
    print("PASS: Step 403 safety review reconciled.")
    print("PASS: Baseline 395 and temporary total 405 validated.")
    print("PASS: Expected added-event total 80 validated.")
    print("PASS: Rollback-only SQL generated.")
    print("SQL:", OUTPUT)


if __name__ == "__main__":
    main()
