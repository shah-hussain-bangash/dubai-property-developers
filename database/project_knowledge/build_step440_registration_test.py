import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PK = ROOT / "database" / "project_knowledge"
REPORTS = PK / "reports"

MANIFEST = REPORTS / "step438_registration_batch14.csv"
REVIEW = REPORTS / "step439_safety_review.csv"
TEMPLATE = PK / "046_test_registration_batch13.sql"
OUTPUT = PK / "048_test_registration_batch14.sql"

DATABASE = "dubai_ai_knowledge_verify_20261019_095633"

EXPECTED_TYPES = {
    "scripts/development/run-tests.ps1": ".ps1",
    "scripts/maintenance/verify_structure.py": ".py",
    "scripts/setup/setup-windows.ps1": ".ps1",
    "tools/__init__.py": ".py",
    "tools/analytics/__init__.py": ".py",
    "tools/analytics/lead_scoring.py": ".py",
    "tools/analytics/tools.py": ".py",
    "tools/base.py": ".py",
    "tools/calendar/__init__.py": ".py",
    "tools/calendar/tools.py": ".py",
}


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    if OUTPUT.exists():
        raise RuntimeError("Step 440 output already exists.")

    batch = read_csv(MANIFEST)
    reviews = read_csv(REVIEW)

    if len(batch) != 10 or len(reviews) != 10:
        raise RuntimeError("Unexpected batch or review count.")

    if {x["source_path"] for x in batch} != set(EXPECTED_TYPES) or len(
        {x["source_path"] for x in batch}
    ) != 10:
        raise RuntimeError("Unexpected fourteenth-batch selection.")

    review_map = {x["source_path"]: x for x in reviews}

    if len(review_map) != 10:
        raise RuntimeError("Duplicate safety-review source paths.")

    tuples = []
    python_count = 0
    powershell_count = 0

    for item in batch:
        path = item["source_path"]
        sha = item["sha256"]
        size = item["size_bytes"]
        extension = EXPECTED_TYPES[path]

        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
            raise RuntimeError(f"Unsafe source path: {path}")

        if any(x in ("", ".", "..") for x in path.split("/")):
            raise RuntimeError(f"Unsafe path component: {path}")

        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise RuntimeError(f"Invalid fingerprint: {path}")

        if not re.fullmatch(r"[0-9]+", size):
            raise RuntimeError(f"Invalid size: {path}")

        required = {
            "priority": "P3",
            "file_type": extension,
            "registration_mode": "metadata_only",
            "execute_source": "false",
            "status": "pending_safety_review",
            "approved_for_live_registration": "false",
        }

        if any(item.get(k) != v for k, v in required.items()):
            raise RuntimeError(f"Manifest mismatch: {path}")

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

        for part in path.split("/"):
            current = current / part

            if current.is_symlink():
                raise RuntimeError(f"Symlink rejected: {path}")

        current.resolve(strict=True).relative_to(ROOT.resolve())

        if not current.is_file():
            raise RuntimeError(f"Missing regular file: {path}")

        # Read data only. Never execute registered project sources.
        data = current.read_bytes()

        if hashlib.sha256(data).hexdigest() != sha:
            raise RuntimeError(f"SHA-256 mismatch: {path}")

        if len(data) != int(size):
            raise RuntimeError(f"Size mismatch: {path}")

        tuples.append(f"('{path}', '{sha}', {size})")

        if extension == ".py":
            python_count += 1
        elif extension == ".ps1":
            powershell_count += 1

    if python_count != 8 or powershell_count != 2:
        raise RuntimeError("Unexpected file-type distribution.")

    sql = TEMPLATE.read_text(encoding="utf-8-sig")

    if f"current_database() <> '{DATABASE}'" not in sql:
        raise RuntimeError("Database guard missing.")

    if not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I):
        raise RuntimeError("Template must end with ROLLBACK.")

    if re.search(r"\bCOMMIT\s*;", sql, re.I):
        raise RuntimeError("Template contains COMMIT.")

    pattern = r"(INSERT INTO step434_batch VALUES\s+)(.+?)(;)"
    matches = list(re.finditer(pattern, sql, re.S))

    if len(matches) != 1:
        raise RuntimeError("Unexpected template VALUES section.")

    match = matches[0]

    sql = sql[: match.start(2)] + ",\n".join(tuples) + sql[match.end(2) :]

    if (
        len(re.findall(r"<> 441\b", sql)) != 4
        or len(re.findall(r"<> 451\b", sql)) != 4
        or len(re.findall(r"\) <> 126\b", sql)) != 1
    ):
        raise RuntimeError("Previous count guards mismatch.")

    # Preserve baseline and temporary post-insert checks separately.
    sql = re.sub(r"<> 451\b", "<> __NEW_TOTAL__", sql)
    sql = re.sub(r"<> 441\b", "<> 451", sql)
    sql = sql.replace("<> __NEW_TOTAL__", "<> 461")
    sql = re.sub(r"\) <> 126\b", ") <> 136", sql)

    sql = sql.replace("step434_batch", "step440_batch")

    old_notice = "All ten thirteenth-batch registrations validated"
    new_notice = "All ten fourteenth-batch registrations validated"

    if sql.count(old_notice) != 1:
        raise RuntimeError("Previous validation notice mismatch.")

    sql = sql.replace(old_notice, new_notice)

    if (
        len(re.findall(r"<> 451\b", sql)) != 4
        or len(re.findall(r"<> 461\b", sql)) != 4
        or len(re.findall(r"\) <> 136\b", sql)) != 1
        or sql.count("IF (SELECT COUNT(*) FROM step440_batch) <> 10 THEN") != 1
        or sql.count("IF v_valid <> 10 THEN") != 1
        or sql.count(new_notice) != 1
        or "Four-table integrity and history verified" not in sql
        or "step434_batch" in sql
        or "__NEW_TOTAL__" in sql
        or not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I)
        or len(re.findall(r"\bROLLBACK\s*;", sql, re.I)) != 1
        or re.search(r"\bCOMMIT\s*;", sql, re.I)
    ):
        raise RuntimeError("Generated SQL safety validation failed.")

    for item in batch:
        tuple_text = f"('{item['source_path']}', '{item['sha256']}', {item['size_bytes']})"

        if sql.count(tuple_text) != 1:
            raise RuntimeError(f"Unexpected tuple count: {item['source_path']}")

    OUTPUT.write_text(sql, encoding="utf-8")

    print("PASS: Ten P3 source fingerprints revalidated.")
    print("PASS: Eight Python and two PowerShell files confirmed.")
    print("PASS: Step 439 safety review reconciled.")
    print("PASS: Baseline 451 and temporary total 461 validated.")
    print("PASS: Added-event target 136 validated.")
    print("PASS: Both ten-file SQL guards preserved.")
    print("PASS: Rollback-only SQL generated.")
    print("PASS: No registered project source files executed.")
    print("File:", OUTPUT)


if __name__ == "__main__":
    main()
