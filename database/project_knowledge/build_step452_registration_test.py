import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PK = ROOT / "database" / "project_knowledge"
REPORTS = PK / "reports"

MANIFEST = REPORTS / "step450_registration_batch16.csv"
REVIEW = REPORTS / "step451_safety_review.csv"
TEMPLATE = PK / "050_test_registration_batch15.sql"
OUTPUT = PK / "052_test_registration_batch16.sql"

DATABASE = "dubai_ai_knowledge_verify_20261019_095633"

EXPECTED_PATHS = {
    "tools/search/__init__.py",
    "tools/search/lead_store.py",
    "tools/search/tools.py",
    "tools/whatsapp/__init__.py",
    "tools/whatsapp/tools.py",
}

def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def replace_exact(text, old, new, count=1):
    if text.count(old) != count:
        raise RuntimeError(f"Expected {count} occurrences: {old}")
    return text.replace(old, new)

def main():
    if OUTPUT.exists():
        raise RuntimeError("Output SQL already exists.")

    batch = read_csv(MANIFEST)
    reviews = read_csv(REVIEW)

    if len(batch) != 5 or len(reviews) != 5:
        raise RuntimeError("Incorrect manifest/review count.")

    if (
        len({x["source_path"] for x in batch}) != 5
        or {x["source_path"] for x in batch} != EXPECTED_PATHS
    ):
        raise RuntimeError("Unexpected final batch paths.")

    review_map = {x["source_path"]: x for x in reviews}

    if len(review_map) != 5 or set(review_map) != EXPECTED_PATHS:
        raise RuntimeError("Invalid review paths.")

    tuples = []

    for item in batch:
        path = item["source_path"]
        sha = item["sha256"]
        size = item["size_bytes"]

        if (
            not re.fullmatch(r"[A-Za-z0-9_./-]+", path)
            or any(p in ("", ".", "..") for p in path.split("/"))
            or not re.fullmatch(r"[0-9a-f]{64}", sha)
            or not re.fullmatch(r"[0-9]+", size)
        ):
            raise RuntimeError(f"Unsafe metadata: {path}")

        required = {
            "priority": "P3",
            "file_type": ".py",
            "registration_mode": "metadata_only",
            "execute_source": "false",
            "status": "pending_safety_review",
            "approved_for_live_registration": "false",
        }

        if any(item.get(k) != v for k, v in required.items()):
            raise RuntimeError(f"Unsafe manifest flags: {path}")

        expected_review = {
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

        review = review_map[path]

        if any(
            review.get(k) != v for k, v in expected_review.items()
        ):
            raise RuntimeError(f"Safety review mismatch: {path}")

        current = ROOT

        for part in path.split("/"):
            current = current / part
            if current.is_symlink():
                raise RuntimeError(f"Symlink rejected: {path}")

        current.resolve(strict=True).relative_to(ROOT.resolve())

        if not current.is_file():
            raise RuntimeError(f"Source missing: {path}")

        # Read bytes only. Never import the source module.
        data = current.read_bytes()

        if (
            hashlib.sha256(data).hexdigest() != sha
            or len(data) != int(size)
        ):
            raise RuntimeError(f"Fingerprint/size mismatch: {path}")

        tuples.append(f"('{path}', '{sha}', {size})")

    sql = TEMPLATE.read_text(encoding="utf-8-sig")

    if (
        f"current_database() <> '{DATABASE}'" not in sql
        or not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I)
        or re.search(r"\bCOMMIT\s*;", sql, re.I)
    ):
        raise RuntimeError("Unsafe SQL template.")

    pattern = r"(INSERT INTO step446_batch VALUES\s+)(.+?)(;)"
    matches = list(re.finditer(pattern, sql, re.S))

    if len(matches) != 1:
        raise RuntimeError("Template VALUES section not unique.")

    match = matches[0]
    sql = (
        sql[:match.start(2)]
        + ",\n".join(tuples)
        + sql[match.end(2):]
    )

    if (
        len(re.findall(r"<> 461\b", sql)) != 4
        or len(re.findall(r"<> 471\b", sql)) != 4
        or len(re.findall(r"\) <> 146\b", sql)) != 1
    ):
        raise RuntimeError("Unexpected template count guards.")

    sql = re.sub(r"<> 471\b", "<> __NEW_TOTAL__", sql)
    sql = re.sub(r"<> 461\b", "<> 471", sql)
    sql = sql.replace("<> __NEW_TOTAL__", "<> 476")
    sql = re.sub(r"\) <> 146\b", ") <> 151", sql)

    sql = replace_exact(
        sql,
        "IF (SELECT COUNT(*) FROM step446_batch) <> 10 THEN",
        "IF (SELECT COUNT(*) FROM step452_batch) <> 5 THEN",
    )
    sql = replace_exact(
        sql, "IF v_valid <> 10 THEN", "IF v_valid <> 5 THEN"
    )
    sql = sql.replace("step446_batch", "step452_batch")

    sql = replace_exact(
        sql,
        "All ten fifteenth-batch registrations validated",
        "All five sixteenth-batch registrations validated",
    )

    if (
        len(re.findall(r"<> 471\b", sql)) != 4
        or len(re.findall(r"<> 476\b", sql)) != 4
        or len(re.findall(r"\) <> 151\b", sql)) != 1
        or sql.count(
            "IF (SELECT COUNT(*) FROM step452_batch) <> 5 THEN"
        ) != 1
        or sql.count("IF v_valid <> 5 THEN") != 1
        or "step446_batch" in sql
        or "__NEW_TOTAL__" in sql
        or "Four-table integrity and history verified" not in sql
        or not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I)
        or len(re.findall(r"\bROLLBACK\s*;", sql, re.I)) != 1
        or re.search(r"\bCOMMIT\s*;", sql, re.I)
    ):
        raise RuntimeError("Generated SQL validation failed.")

    for item in batch:
        entry = (
            f"('{item['source_path']}', "
            f"'{item['sha256']}', {item['size_bytes']})"
        )
        if sql.count(entry) != 1:
            raise RuntimeError("Manifest-to-SQL tuple mismatch.")

    if sql.count("INSERT INTO step452_batch VALUES") != 1:
        raise RuntimeError("SQL temporary batch mismatch.")

    OUTPUT.write_text(sql, encoding="utf-8")

    print("PASS: All five source fingerprints verified.")
    print("PASS: Step 451 safety review reconciled.")
    print("PASS: Baseline 471 and temporary target 476 validated.")
    print("PASS: Added-event target 151 validated.")
    print("PASS: Five-file SQL guards preserved.")
    print("PASS: Final rollback-only SQL generated.")
    print("PASS: No source modules executed.")
    print("SQL:", OUTPUT)

if __name__ == "__main__":
    main()
