import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PK = ROOT / "database" / "project_knowledge"
REPORTS = PK / "reports"

MANIFEST = REPORTS / "step432_registration_batch13.csv"
REVIEW = REPORTS / "step433_safety_review.csv"
TEMPLATE = PK / "044_test_registration_batch12.sql"
OUTPUT = PK / "046_test_registration_batch13.sql"

DATABASE = "dubai_ai_knowledge_verify_20261019_095633"

EXPECTED_TYPES = {
    "schemas/conversations/models.py": ".py",
    "schemas/events/__init__.py": ".py",
    "schemas/events/models.py": ".py",
    "schemas/integrations/__init__.py": ".py",
    "schemas/integrations/models.py": ".py",
    "schemas/leads/__init__.py": ".py",
    "schemas/properties/__init__.py": ".py",
    "schemas/properties/models.py": ".py",
    "scripts/development/demo-lead.ps1": ".ps1",
    "scripts/development/run-api.ps1": ".ps1",
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
        raise RuntimeError("Unexpected manifest/review row count.")

    if {x["source_path"] for x in batch} != set(EXPECTED_TYPES):
        raise RuntimeError("Unexpected thirteenth-batch selection.")

    review_map = {x["source_path"]: x for x in reviews}

    if len(review_map) != 10:
        raise RuntimeError("Duplicate safety-review paths.")

    tuples = []
    seen = set()

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
            raise RuntimeError(f"Invalid file size: {path}")

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

        # Read bytes only; never import or execute source files.
        data = current.read_bytes()

        if hashlib.sha256(data).hexdigest() != sha:
            raise RuntimeError(f"Fingerprint mismatch: {path}")

        if len(data) != int(size):
            raise RuntimeError(f"Size mismatch: {path}")

        tuples.append(f"('{path}', '{sha}', {size})")

    sql = TEMPLATE.read_text(encoding="utf-8-sig")

    if f"current_database() <> '{DATABASE}'" not in sql:
        raise RuntimeError("Database guard missing.")

    if not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I):
        raise RuntimeError("Template must end in ROLLBACK.")

    if re.search(r"\bCOMMIT\s*;", sql, re.I):
        raise RuntimeError("Template contains COMMIT.")

    pattern = r"(INSERT INTO step428_batch VALUES\s+)(.+?)(;)"
    matches = list(re.finditer(pattern, sql, re.S))

    if len(matches) != 1:
        raise RuntimeError("Unexpected template VALUES section.")

    match = matches[0]

    sql = sql[: match.start(2)] + ",\n".join(tuples) + sql[match.end(2) :]

    if (
        len(re.findall(r"<> 431\b", sql)) != 4
        or len(re.findall(r"<> 441\b", sql)) != 4
        or len(re.findall(r"\) <> 116\b", sql)) != 1
    ):
        raise RuntimeError("Previous template count guards mismatch.")

    # Update post-insert checks separately from baseline checks.
    sql = re.sub(r"<> 441\b", "<> __NEW_TOTAL__", sql)
    sql = re.sub(r"<> 431\b", "<> 441", sql)
    sql = sql.replace("<> __NEW_TOTAL__", "<> 451")
    sql = re.sub(r"\) <> 116\b", ") <> 126", sql)

    sql = sql.replace("step428_batch", "step434_batch")

    old_notice = "All ten twelfth-batch registrations validated"
    new_notice = "All ten thirteenth-batch registrations validated"

    if sql.count(old_notice) != 1:
        raise RuntimeError("Unexpected validation notice.")

    sql = sql.replace(old_notice, new_notice)

    if (
        len(re.findall(r"<> 441\b", sql)) != 4
        or len(re.findall(r"<> 451\b", sql)) != 4
        or len(re.findall(r"\) <> 126\b", sql)) != 1
        or sql.count("IF (SELECT COUNT(*) FROM step434_batch) <> 10 THEN") != 1
        or sql.count("IF v_valid <> 10 THEN") != 1
        or new_notice not in sql
        or "Four-table integrity and history verified" not in sql
        or "step428_batch" in sql
        or "__NEW_TOTAL__" in sql
        or not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I)
        or len(re.findall(r"\bROLLBACK\s*;", sql, re.I)) != 1
        or re.search(r"\bCOMMIT\s*;", sql, re.I)
    ):
        raise RuntimeError("Generated SQL safety validation failed.")

    for item in batch:
        entry = f"('{item['source_path']}', '{item['sha256']}', {item['size_bytes']})"

        if sql.count(entry) != 1:
            raise RuntimeError(f"Unexpected SQL tuple count: {item['source_path']}")

    OUTPUT.write_text(sql, encoding="utf-8")

    print("PASS: Ten P3 source fingerprints revalidated.")
    print("PASS: Eight Python and two PowerShell files confirmed.")
    print("PASS: Step 433 safety review reconciled.")
    print("PASS: Baseline 441 and temporary total 451 validated.")
    print("PASS: Added-event total 126 validated.")
    print("PASS: Ten-file SQL guards preserved.")
    print("PASS: Rollback-only SQL generated.")
    print("PASS: No project source files executed.")
    print("File:", OUTPUT)


if __name__ == "__main__":
    main()
