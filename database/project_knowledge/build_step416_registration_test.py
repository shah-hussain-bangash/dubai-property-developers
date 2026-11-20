import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PK = ROOT / "database" / "project_knowledge"
REPORTS = PK / "reports"

MANIFEST = REPORTS / "step414_registration_batch10.csv"
REVIEW = REPORTS / "step415_safety_review.csv"
TEMPLATE = PK / "038_test_registration_batch9.sql"
OUTPUT = PK / "040_test_registration_batch10.sql"

DATABASE = "dubai_ai_knowledge_verify_20261019_095633"

EXPECTED_PATHS = {
    "background_jobs_migration_review.sql",
    "integrations/__init__.py",
    "integrations/bayut/__init__.py",
    "integrations/espocrm/__init__.py",
    "integrations/factory.py",
    "integrations/google/__init__.py",
    "integrations/listing_portal.py",
    "integrations/meta/__init__.py",
    "integrations/n8n/__init__.py",
    "integrations/propertyfinder/__init__.py",
}


def load_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def replace_exact(text, old, new, expected=1):
    count = text.count(old)
    if count != expected:
        raise RuntimeError(
            f"Expected {expected} instances of {old!r}; found {count}"
        )
    return text.replace(old, new)


def main():
    if OUTPUT.exists():
        raise RuntimeError("Step 416 output already exists.")

    batch = load_csv(MANIFEST)
    review = load_csv(REVIEW)

    if len(batch) != 10 or len(review) != 10:
        raise RuntimeError("Expected ten manifest and review rows.")

    if {r["source_path"] for r in batch} != EXPECTED_PATHS:
        raise RuntimeError("Unexpected source file selection.")

    review_map = {r["source_path"]: r for r in review}

    if len(review_map) != 10:
        raise RuntimeError("Duplicate safety review paths.")

    values = []
    seen = set()

    for row in batch:
        path = row["source_path"]
        sha = row["sha256"]
        size = row["size_bytes"]

        if path in seen:
            raise RuntimeError("Duplicate manifest path.")
        seen.add(path)

        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
            raise RuntimeError(f"Unsafe path: {path}")

        if any(part in ("", ".", "..") for part in path.split("/")):
            raise RuntimeError(f"Unsafe path component: {path}")

        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise RuntimeError(f"Invalid hash: {path}")

        if not re.fullmatch(r"[0-9]+", size):
            raise RuntimeError(f"Invalid size: {path}")

        ext = Path(path).suffix.lower()

        if ext not in (".py", ".sql"):
            raise RuntimeError(f"Unexpected file type: {path}")

        required = {
            "priority": "P3",
            "file_type": ext,
            "registration_mode": "metadata_only",
            "execute_source": "false",
            "status": "pending_safety_review",
            "approved_for_live_registration": "false",
        }

        if any(row.get(k) != v for k, v in required.items()):
            raise RuntimeError(f"Manifest mismatch: {path}")

        checked = review_map.get(path)

        review_required = {
            "priority": "P3",
            "file_type": ext,
            "sha256": sha,
            "size_bytes": size,
            "sha256_verified": "true",
            "size_verified": "true",
            "registration_mode": "metadata_only",
            "execute_source": "false",
            "approved_for_live_registration": "false",
            "review_status": "fingerprint_and_type_verified",
        }

        if checked is None or any(
            checked.get(k) != v for k, v in review_required.items()
        ):
            raise RuntimeError(f"Safety review mismatch: {path}")

        current = ROOT

        for component in path.split("/"):
            current = current / component
            if current.is_symlink():
                raise RuntimeError(f"Symlink rejected: {path}")

        current.resolve(strict=True).relative_to(ROOT.resolve())

        if not current.is_file():
            raise RuntimeError(f"Missing source: {path}")

        # Read bytes only. Never import or execute the source.
        contents = current.read_bytes()

        if hashlib.sha256(contents).hexdigest() != sha:
            raise RuntimeError(f"Hash mismatch: {path}")

        if len(contents) != int(size):
            raise RuntimeError(f"Size mismatch: {path}")

        values.append(f"('{path}', '{sha}', {size})")

    sql = TEMPLATE.read_text(encoding="utf-8-sig")

    if f"current_database() <> '{DATABASE}'" not in sql:
        raise RuntimeError("Invalid database guard.")

    if not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I):
        raise RuntimeError("Template does not end with ROLLBACK.")

    if re.search(r"\bCOMMIT\s*;", sql, re.I):
        raise RuntimeError("COMMIT is prohibited.")

    pattern = (
        r"(INSERT INTO step410_batch VALUES\s+)"
        r"(.+?)(;)"
    )

    matches = list(re.finditer(pattern, sql, re.S))

    if len(matches) != 1:
        raise RuntimeError("Unexpected batch VALUES statement.")

    match = matches[0]

    sql = (
        sql[:match.start(2)]
        + ",\n".join(values)
        + sql[match.end(2):]
    )

    sql = replace_exact(
        sql,
        "IF (SELECT COUNT(*) FROM step410_batch) <> 6 THEN",
        "IF (SELECT COUNT(*) FROM step410_batch) <> 10 THEN",
    )

    sql = replace_exact(
        sql,
        "IF v_valid <> 6 THEN",
        "IF v_valid <> 10 THEN",
    )

    if (
        len(re.findall(r"<> 405\b", sql)) != 4
        or len(re.findall(r"<> 411\b", sql)) != 4
        or len(re.findall(r"\) <> 86\b", sql)) != 1
    ):
        raise RuntimeError("Unexpected template baseline guards.")

    # Replace the target count first to avoid replacing new baseline values.
    sql = re.sub(r"<> 411\b", "<> __NEW_TOTAL__", sql)
    sql = re.sub(r"<> 405\b", "<> 411", sql)
    sql = sql.replace("<> __NEW_TOTAL__", "<> 421")
    sql = re.sub(r"\) <> 86\b", ") <> 96", sql)

    sql = sql.replace("step410_batch", "step416_batch")

    sql = replace_exact(
        sql,
        "All six ninth-batch registrations validated",
        "All ten tenth-batch registrations validated",
    )

    if (
        len(re.findall(r"<> 411\b", sql)) != 4
        or len(re.findall(r"<> 421\b", sql)) != 4
        or len(re.findall(r"\) <> 96\b", sql)) != 1
        or sql.count(
            "IF (SELECT COUNT(*) FROM step416_batch) <> 10 THEN"
        ) != 1
        or sql.count("IF v_valid <> 10 THEN") != 1
        or "All ten tenth-batch registrations validated" not in sql
        or "Four-table integrity and history verified" not in sql
        or not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I)
        or len(re.findall(r"\bROLLBACK\s*;", sql, re.I)) != 1
        or re.search(r"\bCOMMIT\s*;", sql, re.I)
        or "__NEW_TOTAL__" in sql
    ):
        raise RuntimeError("Generated SQL guard verification failed.")

    OUTPUT.write_text(sql, encoding="utf-8")

    print("PASS: All ten P3 source fingerprints verified.")
    print("PASS: Step 415 safety review reconciled.")
    print("PASS: Both ten-file count guards validated.")
    print("PASS: Baseline 411 and temporary total 421 validated.")
    print("PASS: Added-event total 96 validated.")
    print("PASS: Rollback-only SQL generated.")
    print("File:", OUTPUT)


if __name__ == "__main__":
    main()
