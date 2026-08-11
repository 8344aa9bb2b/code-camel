import os
from pathlib import Path

import pytest

from app.analysis.pipeline import (
    _group_by_extension,
    analyze_files,
    analyze_repo,
)
from app.analysis.registry import LinterRegistry, default_registry


def test_default_registry_registers_five_linters():
    registry = default_registry()
    names = {l.name for l in registry.all}
    assert names == {"pylint", "bandit", "eslint", "checkstyle", "spotbugs"}


def test_registry_maps_extensions():
    registry = default_registry()
    assert {l.name for l in registry.linters_for_file("a.py")} == {
        "pylint",
        "bandit",
    }
    assert {l.name for l in registry.linters_for_file("a.js")} == {"eslint"}
    assert {l.name for l in registry.linters_for_file("a.tsx")} == {"eslint"}
    assert {l.name for l in registry.linters_for_file("A.java")} == {
        "checkstyle",
        "spotbugs",
    }
    assert registry.linters_for_file("a.rb") == []


def test_registry_dedupes_linters_for_files():
    registry = default_registry()
    linters = registry.linters_for_files(["a.js", "b.ts", "c.py"])
    assert [l.name for l in linters] == ["eslint", "pylint", "bandit"]


def test_registry_rejects_non_linter():
    registry = LinterRegistry()
    with pytest.raises(TypeError):
        registry.register(object())


def test_group_by_extension():
    grouped = _group_by_extension(["a.py", "b.py", "c.js", "d.txt"])
    assert set(grouped[".py"]) == {"a.py", "b.py"}
    assert grouped[".js"] == ["c.js"]
    assert grouped[".txt"] == ["d.txt"]


def test_analyze_files_skips_unsupported():
    report = analyze_files(["foo.txt", "bar.xyz"])
    assert report.files_skipped == ["foo.txt", "bar.xyz"]
    assert report.findings == []


def test_analyze_files_empty(tmp_path):
    report = analyze_files([])
    assert report.files_analyzed == []
    assert report.findings == []


def test_analyze_files_relativizes_paths(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    target = src / "sample.py"
    target.write_text("import os\nprint('hi')\n", encoding="utf-8")

    report = analyze_files(["src/sample.py"], cwd=str(tmp_path))
    assert report.files_analyzed == ["src/sample.py"]
    assert report.findings


def test_analyze_repo_walks_and_filters(tmp_path, monkeypatch):
    (tmp_path / "app").mkdir()
    (tmp_path / "app").joinpath("main.py").write_text(
        "import os\nimport sys\nprint(os)\n", encoding="utf-8"
    )
    (tmp_path / "app").joinpath("main.js").write_text(
        "const x = 1;\nconsole.log(x);\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests").joinpath("t.py").write_text(
        "def f():\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "venv").mkdir()
    (tmp_path / "venv").joinpath("ignore.py").write_text(
        "x=1\n", encoding="utf-8"
    )
    (tmp_path / "app").joinpath("notes.txt").write_text("hello\n", encoding="utf-8")

    # Scoped scan
    report = analyze_repo(str(tmp_path), include=["app"])
    analyzed = set(report.files_analyzed)
    assert analyzed == {"app/main.py", "app/main.js"}
    assert "tests/t.py" not in analyzed
    assert "venv/ignore.py" not in analyzed

    # Full scan excludes default dirs like venv/tests? tests is not excluded.
    report_full = analyze_repo(str(tmp_path))
    analyzed_full = set(report_full.files_analyzed)
    assert "app/main.py" in analyzed_full
    assert "venv/ignore.py" not in analyzed_full  # default excluded
    assert "app/notes.txt" not in analyzed_full  # unsupported ext
    assert "tests/t.py" in analyzed_full
