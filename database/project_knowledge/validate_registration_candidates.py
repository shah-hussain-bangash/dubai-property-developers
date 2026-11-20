"""Step 364: read-only safety screening of source registry candidates."""

import csv
import hashlib
import re
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
ROOT_RESOLVED = ROOT.resolve()

MANIFEST = (
    ROOT / "database" / "project_knowledge" /
    "reports" / "step363_registration_manifest.csv"
)

REPORT_DIR = ROOT / "database" / "project_knowledge" / "reports"

EXPECTED_COUNT = 184
MAX_SCAN_BYTES = 2 * 1024 * 1024

SECRET_PATTERNS = {
    "private_key_marker": re.compile(
        r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----",
        re.IGNORECASE
    ),
    "possible_secret_assignment": re.compile(
        r"""(?i)(?:api[_-]?key|client[_-]?secret|
        access[_-]?token|auth[_-]?token|password|
        secret[_-]?key)\s*[:=]\s*["'][^"' \r\n]{8,}["']""",
        re.VERBOSE
    ),
    "possible_cloud_access_key": re.compile(
        r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"
    ),
    "possible_github_token": re.compile(
        r"\b(?:ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9_]{20,}\b"
    ),
}

FIELDS = [
    "source_path",
    "review_status",
    "validation_status",
    "original_size_bytes",
    "current_size_bytes",
    "sha256",
    "security_flags",
]


def validate(row):
    path_text = row["source_path"].replace("\\", "/")
    status = row["review_status"]

    record = {
        "source_path": path_text,
        "review_status": status,
        "validation_status": "",
        "original_size_bytes": row["size_bytes"],
        "current_size_bytes": "",
        "sha256": "",
        "security_flags": "",
    }

    flags = []

    parts = path_text.split("/")

    if (
        not path_text
        or path_text.startswith("/")
        or ":" in path_text
        or any(part in ("", ".", "..") for part in parts)
    ):
        record["validation_status"] = "unsafe_path"
        return record

    relative = PurePosixPath(path_text)
    target = ROOT.joinpath(*relative.parts)

    try:
        resolved = target.resolve(strict=False)
        resolved.relative_to(ROOT_RESOLVED)

        # Reject symbolic links anywhere in the path.
        current = ROOT

        for part in relative.parts:
            current = current / part

            if current.is_symlink():
                record["validation_status"] = "unsafe_path"
                return record

        if not target.exists():
            record["validation_status"] = "missing"
            return record

        if not target.is_file():
            record["validation_status"] = "not_regular_file"
            return record

        current_size = target.stat().st_size
        record["current_size_bytes"] = current_size

        if current_size != int(row["size_bytes"]):
            flags.append("size_changed_since_step361")

        if current_size > MAX_SCAN_BYTES:
            record["validation_status"] = "manual_large_file_review"
            record["security_flags"] = ",".join(flags)
            return record

        # Read a bounded file into memory, with no content output.
        data = target.read_bytes()

        if len(data) != current_size:
            flags.append("file_changed_during_scan")

        record["sha256"] = hashlib.sha256(data).hexdigest()

        content = data.decode("utf-8", errors="replace")

        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                flags.append(name)

        # Some files require human review regardless of scan result.
        if status == "security_review_required":
            flags.append("mandatory_security_review")
        elif status == "knowledge_tool_review_required":
            flags.append("mandatory_knowledge_tool_review")
        elif status == "defer_generated_metadata":
            flags.append("generated_metadata_deferred")

        if flags:
            record["validation_status"] = "review_required"
        else:
            record["validation_status"] = "preliminary_scan_clear"

        record["security_flags"] = ",".join(sorted(set(flags)))

    except (OSError, ValueError, UnicodeError):
        record["validation_status"] = "inspection_error"

    return record


def main():
    if not MANIFEST.is_file():
        raise RuntimeError("Step 363 manifest not found")

    with MANIFEST.open(
        newline="", encoding="utf-8-sig"
    ) as stream:
        rows = list(csv.DictReader(stream))

    if len(rows) != EXPECTED_COUNT:
        raise RuntimeError(
            f"Unexpected manifest count: {len(rows)}"
        )

    paths = [row["source_path"] for row in rows]

    if len(set(paths)) != EXPECTED_COUNT:
        raise RuntimeError("Duplicate paths detected")

    results = [validate(row) for row in rows]
    counts = Counter(
        row["validation_status"] for row in results
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = REPORT_DIR / (
        f"step364_candidate_validation_{timestamp}.csv"
    )

    with output.open(
        "x", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(results)

    print("PASS: Manifest entries processed:", len(results))

    print("\nValidation summary:")

    for name, count in sorted(counts.items()):
        print(f"{name}: {count}")

    print("\nFlagged file paths (first 30):")

    flagged = [
        row for row in results
        if row["validation_status"] != "preliminary_scan_clear"
    ]

    for row in flagged[:30]:
        print(
            row["validation_status"],
            row["source_path"],
            row["security_flags"]
        )

    print("\nReport:", output)
    print("Approved registrations: 0")
    print("PASS: Step 364 read-only screening completed")


if __name__ == "__main__":
    main()
