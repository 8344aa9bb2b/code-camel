from app.analysis.finding import Finding, Severity
from app.analysis.pipeline import AnalysisReport
from app.reviewer import build_summary


def test_build_summary_clean():
    report = AnalysisReport(files_analyzed=["a.py"])
    body = build_summary(report)
    assert "No issues found" in body
    assert "Code Review Agent" in body


def test_build_summary_findings():
    report = AnalysisReport(
        files_analyzed=["src/app.py"],
        findings=[
            Finding(
                linter="pylint",
                rule="E0102",
                message="function already defined",
                severity=Severity.ERROR,
                file="src/app.py",
                line=42,
            ),
            Finding(
                linter="bandit",
                rule="B602",
                message="shell injection",
                severity=Severity.ERROR,
                file="src/app.py",
                line=7,
            ),
        ],
    )
    body = build_summary(report)
    assert "Found **2** finding(s)" in body
    assert "pylint / E0102" in body
    assert "bandit / B602" in body
    assert "severity breakdown" in body.lower()


def test_build_summary_skipped_linters():
    from app.analysis.finding import LintRunResult

    report = AnalysisReport(
        files_analyzed=["a.py"],
        findings=[
            Finding(
                linter="eslint",
                rule="no-unused-vars",
                message="x is never used",
                severity=Severity.WARNING,
                file="a.js",
            )
        ],
        results=[LintRunResult(linter="checkstyle", skipped=True)],
    )
    body = build_summary(report)
    assert "Linters skipped: checkstyle" in body
