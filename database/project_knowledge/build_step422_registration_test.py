import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PK = ROOT / "database" / "project_knowledge"
REPORTS = PK / "reports"

MANIFEST = REPORTS / "step420_registration_batch11.csv"
REVIEW = REPORTS / "step421_safety_review.csv"
TEMPLATE = PK / "040_test_registration_batch10.sql"
OUTPUT = PK / "042_test_registration_batch11.sql"

DATABASE = "dubai_ai_knowledge_verify_20261019_095633"

EXPECTED_PATHS = {
    "integrations/slack/__init__.py",
    "integrations/telephony/__init__.py",
    "knowledge/__init__.py",
    "knowledge/documents/__init__.py",
    "knowledge/documents/demo_corpus.py",
    "knowledge/embeddings/__init__.py",
    "knowledge/embeddings/base.py",
    "knowledge/evaluation/__init__.py",
    "knowledge/ingestion/__init__.py",
    "knowledge/retrieval/__init__.py",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def replace_exact(text: str, old: str, new: str, count: int = 1) -> str:
    if text.count(old) != count:
        raise RuntimeError(f"Expected {count} occurrence(s): {old}")
    return text.replace(old, new)


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError("Output SQL already exists.")

    batch = read_csv(MANIFEST)
    reviews = read_csv(REVIEW)

    if len(batch) != 10 or len(reviews) != 10:
        raise RuntimeError("Invalid manifest or review row count.")

    if {x["source_path"] for x in batch} != EXPECTED_PATHS:
        raise RuntimeError("Unexpected eleventh-batch selection.")

    review_map = {x["source_path"]: x for x in reviews}
    if len(review_map) != 10:
        raise RuntimeError("Duplicate review paths.")

    tuples = []
    seen = set()

    for item in batch:
        path = item["source_path"]
        sha = item["sha256"]
        size = item["size_bytes"]

        if path in seen:
            raise RuntimeError(f"Duplicate manifest path: {path}")
        seen.add(path)

        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
            raise RuntimeError(f"Unsafe path: {path}")

        if any(c in ("", ".", "..") for c in path.split("/")):
            raise RuntimeError(f"Unsafe path component: {path}")

        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise RuntimeError(f"Invalid SHA-256: {path}")

        if not re.fullmatch(r"[0-9]+", size):
            raise RuntimeError(f"Invalid size: {path}")

        required = {
            "priority": "P3",
            "file_type": ".py",
            "registration_mode": "metadata_only",
            "execute_source": "false",
            "status": "pending_safety_review",
            "approved_for_live_registration": "false",
        }

        if any(item.get(k) != v for k, v in required.items()):
            raise RuntimeError(f"Manifest restriction failed: {path}")

        checked = review_map.get(path)

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

        if checked is None or any(checked.get(k) != v for k, v in review_required.items()):
            raise RuntimeError(f"Review mismatch: {path}")

        current = ROOT

        for component in path.split("/"):
            current = current / component
            if current.is_symlink():
                raise RuntimeError(f"Symlink rejected: {path}")

        current.resolve(strict=True).relative_to(ROOT.resolve())

        if not current.is_file():
            raise RuntimeError(f"Missing source file: {path}")

        # Read only: do not import or execute project source code.
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

    pattern = (
        r"(INSERT INTO step416_batch VALUES\s+)"
        r"(.+?)(;)"
    )

    matches = list(re.finditer(pattern, sql, re.S))

    if len(matches) != 1:
        raise RuntimeError("Unexpected template VALUES section.")

    match = matches[0]

    sql = sql[: match.start(2)] + ",\n".join(tuples) + sql[match.end(2) :]

    if (
        len(re.findall(r"<> 411\b", sql)) != 4
        or len(re.findall(r"<> 421\b", sql)) != 4
        or len(re.findall(r"\) <> 96\b", sql)) != 1
    ):
        raise RuntimeError("Template count guards do not match Step 416.")

    # Replace old post-insert total before the old baseline.
    sql = re.sub(r"<> 421\b", "<> __NEW_TOTAL__", sql)
    sql = re.sub(r"<> 411\b", "<> 421", sql)
    sql = sql.replace("<> __NEW_TOTAL__", "<> 431")
    sql = re.sub(r"\) <> 96\b", ") <> 106", sql)

    sql = replace_exact(
        sql,
        "step416_batch",
        "step422_batch",
        count=sql.count("step416_batch"),
    )

    sql = replace_exact(
        sql,
        "All ten tenth-batch registrations validated",
        "All ten eleventh-batch registrations validated",
    )

    if (
        len(re.findall(r"<> 421\b", sql)) != 4
        or len(re.findall(r"<> 431\b", sql)) != 4
        or len(re.findall(r"\) <> 106\b", sql)) != 1
        or sql.count("IF (SELECT COUNT(*) FROM step422_batch) <> 10 THEN") != 1
        or sql.count("IF v_valid <> 10 THEN") != 1
        or "All ten eleventh-batch registrations validated" not in sql
        or "Four-table integrity and history verified" not in sql
        or not re.search(r"\bROLLBACK\s*;\s*$", sql, re.I)
        or len(re.findall(r"\bROLLBACK\s*;", sql, re.I)) != 1
        or re.search(r"\bCOMMIT\s*;", sql, re.I)
        or "__NEW_TOTAL__" in sql
        or "step416_batch" in sql
    ):
        raise RuntimeError("Generated SQL safety validation failed.")

    OUTPUT.write_text(sql, encoding="utf-8")

    print("PASS: All ten eleventh-batch source fingerprints verified.")
    print("PASS: Step 421 safety review reconciled.")
    print("PASS: Baseline 421 and temporary total 431 validated.")
    print("PASS: Added-event total 106 validated.")
    print("PASS: Ten-file SQL guards preserved.")
    print("PASS: Rollback-only SQL generated.")
    print("PASS: No source files executed.")
    print("File:", OUTPUT)


if __name__ == "__main__":
    main()
