import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PK = ROOT / "database" / "project_knowledge"
REPORTS = PK / "reports"

MANIFEST = REPORTS / "step426_registration_batch12.csv"
REVIEW = REPORTS / "step427_safety_review.csv"
TEMPLATE = PK / "042_test_registration_batch11.sql"
OUTPUT = PK / "044_test_registration_batch12.sql"

DATABASE = "dubai_ai_knowledge_verify_20261019_095633"

EXPECTED_TYPES = {
    "knowledge/vectorstores/__init__.py": ".py",
    "knowledge/vectorstores/base.py": ".py",
    "live_api_acceptance_test.py": ".py",
    "migration_0004_only.sql": ".sql",
    "migration_0005_review.sql": ".sql",
    "migration_0006_review.sql": ".sql",
    "schemas/__init__.py": ".py",
    "schemas/agents/__init__.py": ".py",
    "schemas/agents/models.py": ".py",
    "schemas/conversations/__init__.py": ".py",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError("Output SQL already exists.")

    batch = read_csv(MANIFEST)
    reviews = read_csv(REVIEW)

    if len(batch) != 10 or len(reviews) != 10:
        raise RuntimeError("Unexpected manifest or review count.")

    if {x["source_path"] for x in batch} != set(EXPECTED_TYPES):
        raise RuntimeError("Unexpected twelfth-batch selection.")

    review_map = {x["source_path"]: x for x in reviews}

    if len(review_map) != 10:
        raise RuntimeError("Duplicate review records.")

    seen = set()
    tuples = []

    for item in batch:
        path = item["source_path"]
        sha = item["sha256"]
        size = item["size_bytes"]

        if path in seen:
            raise RuntimeError(f"Duplicate source: {path}")
        seen.add(path)

        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
            raise RuntimeError(f"Unsafe path: {path}")

        if any(x in ("", ".", "..") for x in path.split("/")):
            raise RuntimeError(f"Unsafe path component: {path}")

        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise RuntimeError(f"Invalid SHA-256: {path}")

        if not re.fullmatch(r"[0-9]+", size):
            raise RuntimeError(f"Invalid size: {path}")

        extension = EXPECTED_TYPES[path]

        required = {
            "priority": "P3",
            "file_type": extension,
            "registration_mode": "metadata_only",
            "execute_source": "false",
            "status": "pending_safety_review",
            "approved_for_live_registration": "false",
        }

        if any(item.get(k) != v for k, v in required.items()):
            raise RuntimeError(f"Manifest restriction mismatch: {path}")

        review = review_map.get(path)

        review_required = {
            "priority": "P3",
            "file_type": extension,
            "sha256": sha,
            "size_bytes": size,
            "sha256_verified": "true",
            "size_verified": "true",
            "registration_mode": "metadata_only",
            "execute_source": "false",
            "approved_for_live_registration": "false",
            "review_status": "fingerprint_and_type_verified",
        }

        if review is None or any(review.get(k) != v for k, v in review_required.items()):
            raise RuntimeError(f"Safety review mismatch: {path}")

        current = ROOT

        for component in path.split("/"):
            current = current / component
            if current.is_symlink():
                raise RuntimeError(f"Symlink rejected: {path}")

        current.resolve(strict=True).relative_to(ROOT.resolve())

        if not current.is_file():
            raise RuntimeError(f"Missing source file: {path}")

        # Read bytes only. Do not import Python or execute SQL source files.
        data = current.read_bytes()

        if hashlib.sha256(data).hexdigest() != sha:
            raise RuntimeError(f"Fingerprint mismatch: {path}")

        if len(data) != int(size):
            raise RuntimeError(f"File size mismatch: {path}")

        tuples.append(f"('{path}', '{sha}', {size})")

    sql = TEMPLATE.read_text(encoding="utf-8-sig")

    if f"current_database() <> '{DATABASE}'" not in sql:
        raise RuntimeError("Database guard missing.")

    if not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I):
        raise RuntimeError("Template does not end in ROLLBACK.")

    if re.search(r"\bCOMMIT\s*;", sql, re.I):
        raise RuntimeError("Template contains COMMIT.")

    pattern = r"(INSERT INTO step422_batch VALUES\s+)(.+?)(;)"

    matches = list(re.finditer(pattern, sql, re.S))

    if len(matches) != 1:
        raise RuntimeError("Unexpected template VALUES section.")

    match = matches[0]

    sql = sql[: match.start(2)] + ",\n".join(tuples) + sql[match.end(2) :]

    if (
        len(re.findall(r"<> 421\b", sql)) != 4
        or len(re.findall(r"<> 431\b", sql)) != 4
        or len(re.findall(r"\) <> 106\b", sql)) != 1
    ):
        raise RuntimeError("Unexpected previous-batch count guards.")

    # Preserve the distinction between baseline and post-insert guards.
    sql = re.sub(r"<> 431\b", "<> __NEW_TOTAL__", sql)
    sql = re.sub(r"<> 421\b", "<> 431", sql)
    sql = sql.replace("<> __NEW_TOTAL__", "<> 441")
    sql = re.sub(r"\) <> 106\b", ") <> 116", sql)

    sql = sql.replace("step422_batch", "step428_batch")

    if "step422_batch" in sql:
        raise RuntimeError("Old temporary table name remains.")

    if sql.count("step428_batch") == 0:
        raise RuntimeError("New temporary table name missing.")

    old_notice = "All ten eleventh-batch registrations validated"
    new_notice = "All ten twelfth-batch registrations validated"

    if sql.count(old_notice) != 1:
        raise RuntimeError("Unexpected validation notice.")

    sql = sql.replace(old_notice, new_notice)

    if (
        len(re.findall(r"<> 431\b", sql)) != 4
        or len(re.findall(r"<> 441\b", sql)) != 4
        or len(re.findall(r"\) <> 116\b", sql)) != 1
        or sql.count("IF (SELECT COUNT(*) FROM step428_batch) <> 10 THEN") != 1
        or sql.count("IF v_valid <> 10 THEN") != 1
        or new_notice not in sql
        or "Four-table integrity and history verified" not in sql
        or not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I)
        or len(re.findall(r"\bROLLBACK\s*;", sql, re.I)) != 1
        or re.search(r"\bCOMMIT\s*;", sql, re.I)
        or "__NEW_TOTAL__" in sql
    ):
        raise RuntimeError("Generated rollback SQL validation failed.")

    # Ensure each source tuple occurs once.
    for item in batch:
        entry = f"('{item['source_path']}', '{item['sha256']}', {item['size_bytes']})"
        if sql.count(entry) != 1:
            raise RuntimeError(f"Expected exactly one SQL tuple: {item['source_path']}")

    OUTPUT.write_text(sql, encoding="utf-8")

    print("PASS: All ten source fingerprints revalidated.")
    print("PASS: Seven Python and three SQL source files confirmed.")
    print("PASS: Step 427 safety review reconciled.")
    print("PASS: Database baseline 431 and temporary total 441 validated.")
    print("PASS: Added-event target 116 validated.")
    print("PASS: Both ten-file SQL guards preserved.")
    print("PASS: Rollback-only SQL generated.")
    print("PASS: No project source modules or migrations executed.")
    print("File:", OUTPUT)


if __name__ == "__main__":
    main()
