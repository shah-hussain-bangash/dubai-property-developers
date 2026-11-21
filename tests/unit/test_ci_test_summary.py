"""Check result accounting across pytest and Vitest report shapes."""

import xml.etree.ElementTree as ET

import pytest

from scripts.maintenance.summarize_test_report import main, render_summary


def test_pytest_outcomes_distinguish_known_failures_from_skips(tmp_path):
    report = tmp_path / "pytest.xml"
    report.write_text(
        '<testsuites><testsuite tests="999"><testcase name="ok"/>'
        '<testcase><skipped type="pytest.skip"/></testcase>'
        '<testcase><skipped type="pytest.xfail"/></testcase>'
        "<testcase><failure/></testcase><testcase><error/></testcase>"
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    summary = render_summary(report, "Backend")
    for outcome in ["Passed", "Skipped", "Expected failures", "Failures", "Errors"]:
        assert f"| {outcome} | 1 |" in summary
    assert "| Total | 5 |" in summary
    assert "Expected failures remain unresolved" in summary


def test_vitest_nested_suites_and_line_coverage(tmp_path):
    report, coverage = tmp_path / "vitest.xml", tmp_path / "coverage.xml"
    report.write_text(
        "<testsuites><testsuite><testcase/><testsuite><testcase/>"
        "</testsuite></testsuite></testsuites>",
        encoding="utf-8",
    )
    coverage.write_text('<coverage lines-covered="3" lines-valid="4"/>', encoding="utf-8")
    summary = render_summary(report, "Frontend", coverage)
    assert "| Passed | 2 |" in summary
    assert "| Total | 2 |" in summary
    assert "75.0%" in summary
    assert "(3/4 lines)" in summary


def test_missing_report_does_not_claim_tests_passed(tmp_path):
    summary = render_summary(tmp_path / "missing.xml", "Tests\n| details")
    assert "report unavailable" in summary
    assert "no test outcome inferred" in summary
    assert "| Passed |" not in summary
    assert summary.startswith("## Tests \\| details\n")


def test_malformed_report_is_reported_as_an_error(tmp_path):
    report = tmp_path / "broken.xml"
    report.write_text("<testsuite>", encoding="utf-8")
    with pytest.raises(ET.ParseError):
        render_summary(report, "Tests")


def test_impossible_coverage_is_not_presented_as_valid(tmp_path):
    report, coverage = tmp_path / "test.xml", tmp_path / "coverage.xml"
    report.write_text("<testsuite><testcase/></testsuite>", encoding="utf-8")
    coverage.write_text('<coverage lines-covered="5" lines-valid="4"/>', encoding="utf-8")
    with pytest.raises(ValueError, match="Coverage line counts"):
        render_summary(report, "Tests", coverage)


def test_entity_declarations_are_rejected_before_parsing(tmp_path):
    report = tmp_path / "entities.xml"
    report.write_text(
        '<!DOCTYPE testsuite [<!ENTITY label "expanded">]>'
        '<testsuite><testcase name="&label;"/></testsuite>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="DTD or entity"):
        render_summary(report, "Tests")


def test_cli_appends_to_github_summary_and_logs_counts(tmp_path, monkeypatch, capsys):
    report, destination = tmp_path / "test.xml", tmp_path / "summary.md"
    report.write_text("<testsuite><testcase/></testsuite>", encoding="utf-8")
    destination.write_text("Existing summary\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(destination))
    monkeypatch.setattr("sys.argv", ["summary", str(report), "--label", "CI tests"])
    main()
    output = destination.read_text(encoding="utf-8")
    assert output.startswith("Existing summary\n## CI tests\n")
    assert "| Passed | 1 |" in output
    assert "| Passed | 1 |" in capsys.readouterr().out
