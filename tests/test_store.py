import pytest

from app.analysis.finding import Finding, Severity
from app.analysis.pipeline import AnalysisReport
from app import store


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    store._reset_path(str(tmp_path / "test.db"))
    yield
    store._reset_path(":memory:")


def _report(*findings) -> AnalysisReport:
    return AnalysisReport(findings=list(findings))


def test_save_and_read_roundtrip():
    report = _report(
        Finding(
            linter="pylint",
            rule="E0102",
            message="function already defined",
            severity=Severity.ERROR,
            file="src/app.py",
            line=42,
        )
    )
    store.save_pr_review("acme/web", 3, "abc123", report, [])

    review = store.get_pr_review("acme/web", 3)
    assert review["count"] == 1
    assert "src/app.py" in review["files"]
    item = review["files"]["src/app.py"][0]
    assert item["rule"] == "E0102"
    assert item["line"] == 42


def test_save_replaces_previous_review():
    r1 = _report(
        Finding(
            linter="pylint", rule="A", message="old", severity=Severity.WARNING,
            file="a.py", line=1,
        )
    )
    store.save_pr_review("acme/web", 3, "sha1", r1, [])
    r2 = _report(
        Finding(
            linter="pylint", rule="B", message="new", severity=Severity.ERROR,
            file="a.py", line=2,
        )
    )
    store.save_pr_review("acme/web", 3, "sha2", r2, [])

    review = store.get_pr_review("acme/web", 3)
    assert review["count"] == 1
    assert review["files"]["a.py"][0]["rule"] == "B"


def test_prs_are_isolated():
    store.save_pr_review(
        "acme/web", 1, "s",
        _report(Finding(
            linter="bandit", rule="B602", message="x", severity=Severity.ERROR,
            file="a.py", line=5,
        )),
        [],
    )
    assert store.get_pr_review("acme/web", 2)["count"] == 0


def test_suggestions_stored_with_source():
    from app.ai.code_smell import RefactorSuggestion

    store.save_pr_review(
        "acme/web", 4, "s",
        AnalysisReport(),
        [
            RefactorSuggestion(
                file="a.py", line=10, message="extract method",
                severity=Severity.SUGGESTION,
            )
        ],
    )
    review = store.get_pr_review("acme/web", 4)
    assert review["count"] == 1
    item = review["files"]["a.py"][0]
    assert item["source"] == "ai"
    assert item["linter"] == "ai"
    assert item["message"] == "extract method"
