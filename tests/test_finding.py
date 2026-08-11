import json

from app.analysis.finding import Finding, Severity


def test_finding_to_dict_roundtrip():
    f = Finding(
        linter="pylint",
        rule="undefined-variable",
        message="Undefined variable 'x'",
        severity=Severity.ERROR,
        file="src/app.py",
        line=3,
        column=5,
        end_line=3,
        end_column=6,
    )
    d = f.to_dict()
    assert d["linter"] == "pylint"
    assert d["rule"] == "undefined-variable"
    assert d["severity"] == "error"
    assert d["file"] == "src/app.py"
    assert d["line"] == 3
    assert d["column"] == 5
    assert d["end_line"] == 3


def test_severity_enum_values():
    assert [s.value for s in Severity] == [
        "critical",
        "error",
        "warning",
        "suggestion",
    ]
