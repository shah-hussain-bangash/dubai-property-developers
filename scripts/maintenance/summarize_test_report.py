"""Summarize locally generated pytest/Vitest JUnit reports without changing test outcomes."""

from __future__ import annotations

import argparse
import os
import xml.etree.ElementTree as ET
from pathlib import Path


def read_report(path: Path) -> ET.Element:
    with path.open(encoding="utf-8-sig") as source:
        content = source.read(10_000_001)
    if len(content) > 10_000_000:
        raise ValueError("XML report exceeds the summary size limit")
    if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
        raise ValueError("XML report must not contain DTD or entity declarations")
    # Reports are bounded UTF-8; DTD/entity declarations are rejected before parsing.
    return ET.fromstring(content)  # noqa: S314 -- See the explicit input guards above.


def render_summary(report: Path, label: str, coverage: Path | None = None) -> str:
    heading = label.replace("\n", " ").replace("\r", " ").replace("|", "\\|")
    lines = [f"## {heading}", ""]
    if not report.is_file():
        return "\n".join([*lines, "JUnit report unavailable; no test outcome inferred.", ""])
    root = read_report(report)
    if root.tag not in {"testsuites", "testsuite"}:
        raise ValueError("Expected a JUnit testsuite or testsuites document")
    counts = {"Passed": 0, "Skipped": 0, "Expected failures": 0, "Failures": 0, "Errors": 0}
    for case in root.iter("testcase"):
        skip = case.find("skipped")
        if case.find("error") is not None:
            outcome = "Errors"
        elif case.find("failure") is not None:
            outcome = "Failures"
        elif skip is not None:
            outcome = "Expected failures" if skip.get("type") == "pytest.xfail" else "Skipped"
        else:
            outcome = "Passed"
        counts[outcome] += 1
    lines.extend(["| Outcome | Tests |", "|---|---:|"])
    lines.extend(f"| {name} | {count} |" for name, count in counts.items())
    lines.extend([f"| Total | {sum(counts.values())} |", ""])
    if coverage is not None and coverage.is_file():
        attributes = read_report(coverage).attrib
        covered, valid = int(attributes["lines-covered"]), int(attributes["lines-valid"])
        if valid <= 0 or not 0 <= covered <= valid:
            raise ValueError("Coverage line counts are invalid")
        lines.extend([f"Line coverage: **{covered / valid:.1%}** ({covered}/{valid} lines).", ""])
    lines.extend(
        [
            "Counts describe this report only. Expected failures remain unresolved test scenarios.",
            "Download the matching artifact for individual test details.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--label", default="Test results")
    parser.add_argument("--coverage", type=Path)
    args = parser.parse_args()
    summary = render_summary(args.report, args.label, args.coverage)
    print(summary)
    destination = os.environ.get("GITHUB_STEP_SUMMARY")
    if destination:
        with Path(destination).open("a", encoding="utf-8") as output:
            output.write(summary + "\n")


if __name__ == "__main__":
    main()
