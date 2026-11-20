import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PK = ROOT / "database" / "project_knowledge"
REPORTS = PK / "reports"

MANIFEST = REPORTS / "step444_registration_batch15.csv"
REVIEW = REPORTS / "step445_safety_review.csv"
TEMPLATE = PK / "048_test_registration_batch14.sql"
OUTPUT = PK / "050_test_registration_batch15.sql"

DATABASE = "dubai_ai_knowledge_verify_20261019_095633"

EXPECTED_PATHS = {
    "tools/crm/__init__.py",
    "tools/documents/__init__.py",
    "tools/documents/tools.py",
    "tools/email/__init__.py",
    "tools/email/sender.py",
    "tools/email/templates.py",
    "tools/email/tools.py",
    "tools/property/__init__.py",
    "tools/property/catalog.py",
    "tools/property/tools.py",
}


def load_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main():
    if OUTPUT.exists():
        raise RuntimeError("Step 446 SQL already exists.")

    batch = load_csv(MANIFEST)
    reviews = load_csv(REVIEW)

    if len(batch) != 10 or len(reviews) != 10:
        raise RuntimeError("Unexpected manifest or review count.")

    if {r["source_path"] for r in batch} != EXPECTED_PATHS or len(
        {r["source_path"] for r in batch}
    ) != 10:
        raise RuntimeError("Unexpected fifteenth-batch selection.")

    review_map = {r["source_path"]: r for r in reviews}

    if len(review_map) != 10 or set(review_map) != EXPECTED_PATHS:
        raise RuntimeError("Safety review path mismatch.")

    tuples = []

    for item in batch:
        path = item["source_path"]
        sha = item["sha256"]
        size = item["size_bytes"]

        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
            raise RuntimeError(f"Unsafe path: {path}")

        if any(part in ("", ".", "..") for part in path.split("/")):
            raise RuntimeError(f"Unsafe path component: {path}")

        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise RuntimeError(f"Invalid SHA-256: {path}")

        if not re.fullmatch(r"[0-9]+", size):
            raise RuntimeError(f"Invalid file size: {path}")

        required = {
            "priority": "P3",
            "file_type": ".py",
            "registration_mode": "metadata_only",
            "execute_source": "false",
            "status": "pending_safety_review",
            "approved_for_live_registration": "false",
        }

        if any(item.get(k) != v for k, v in required.items()):
            raise RuntimeError(f"Unsafe manifest entry: {path}")

        review_required = {
            "priority": "P3",
            "file_type": ".py",
            "sha256": sha,
            "size_bytes": size,
            "sha256_verified": "true",
            "size_verified": "true",
            "registration_mode": "metadata_only",
            "execute_source": "false",
            "approved_for_live_registration": "false",
            "review_status": "fingerprint_and_type_verified",
        }

        review = review_map.get(path)

        if review is None or any(review.get(k) != v for k, v in review_required.items()):
            raise RuntimeError(f"Review mismatch: {path}")

        current = ROOT

        for component in path.split("/"):
            current = current / component

            if current.is_symlink():
                raise RuntimeError(f"Symlink rejected: {path}")

        current.resolve(strict=True).relative_to(ROOT.resolve())

        if not current.is_file():
            raise RuntimeError(f"Missing source file: {path}")

        # File inspection only; no Python source imports.
        data = current.read_bytes()

        if hashlib.sha256(data).hexdigest() != sha:
            raise RuntimeError(f"Fingerprint mismatch: {path}")

        if len(data) != int(size):
            raise RuntimeError(f"Size mismatch: {path}")

        tuples.append(f"('{path}', '{sha}', {size})")

    sql = TEMPLATE.read_text(encoding="utf-8-sig")

    if f"current_database() <> '{DATABASE}'" not in sql:
        raise RuntimeError("Target-database guard missing.")

    if not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I):
        raise RuntimeError("Template must end with ROLLBACK.")

    if re.search(r"\bCOMMIT\s*;", sql, re.I):
        raise RuntimeError("Template contains COMMIT.")

    pattern = r"(INSERT INTO step440_batch VALUES\s+)(.+?)(;)"
    matches = list(re.finditer(pattern, sql, re.S))

    if len(matches) != 1:
        raise RuntimeError("Template VALUES section mismatch.")

    match = matches[0]

    sql = sql[: match.start(2)] + ",\n".join(tuples) + sql[match.end(2) :]

    if (
        len(re.findall(r"<> 451\b", sql)) != 4
        or len(re.findall(r"<> 461\b", sql)) != 4
        or len(re.findall(r"\) <> 136\b", sql)) != 1
    ):
        raise RuntimeError("Template count guards mismatch.")

    sql = re.sub(r"<> 461\b", "<> __NEW_TOTAL__", sql)
    sql = re.sub(r"<> 451\b", "<> 461", sql)
    sql = sql.replace("<> __NEW_TOTAL__", "<> 471")
    sql = re.sub(r"\) <> 136\b", ") <> 146", sql)

    sql = sql.replace("step440_batch", "step446_batch")

    old_notice = "All ten fourteenth-batch registrations validated"
    new_notice = "All ten fifteenth-batch registrations validated"

    if sql.count(old_notice) != 1:
        raise RuntimeError("Previous notice mismatch.")

    sql = sql.replace(old_notice, new_notice)

    if (
        len(re.findall(r"<> 461\b", sql)) != 4
        or len(re.findall(r"<> 471\b", sql)) != 4
        or len(re.findall(r"\) <> 146\b", sql)) != 1
        or sql.count("IF (SELECT COUNT(*) FROM step446_batch) <> 10 THEN") != 1
        or sql.count("IF v_valid <> 10 THEN") != 1
        or sql.count(new_notice) != 1
        or "Four-table integrity and history verified" not in sql
        or "step440_batch" in sql
        or "__NEW_TOTAL__" in sql
        or not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I)
        or len(re.findall(r"\bROLLBACK\s*;", sql, re.I)) != 1
        or re.search(r"\bCOMMIT\s*;", sql, re.I)
    ):
        raise RuntimeError("Generated SQL safety checks failed.")

    for item in batch:
        entry = f"('{item['source_path']}', '{item['sha256']}', {item['size_bytes']})"
        if sql.count(entry) != 1:
            raise RuntimeError(f"SQL tuple mismatch: {item['source_path']}")

    OUTPUT.write_text(sql, encoding="utf-8")

    print("PASS: All ten P3 Python source fingerprints verified.")
    print("PASS: Step 445 safety review reconciled.")
    print("PASS: Baseline 461 and temporary total 471 validated.")
    print("PASS: Added-event target 146 validated.")
    print("PASS: Both ten-file count guards preserved.")
    print("PASS: Rollback-only SQL generated.")
    print("PASS: No registered Python source files executed.")
    print("File:", OUTPUT)


if __name__ == "__main__":
    main()
