from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .base import Linter
from .finding import Finding, LintRunResult, Severity
from .registry import LinterRegistry, default_registry

# Extensions we know how to analyze with at least one bundled linter.
_SUPPORTED_EXTENSIONS = frozenset(
    {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java"}
)


@dataclass
class AnalysisReport:
    """Aggregated result of running every applicable linter."""

    findings: list[Finding] = field(default_factory=list)
    results: list[LintRunResult] = field(default_factory=list)
    files_analyzed: list[str] = field(default_factory=list)
    files_skipped: list[str] = field(default_factory=list)

    @property
    def errors(self) -> List[str]:
        return [e for r in self.results for e in r.errors]

    @property
    def counts_by_severity(self) -> Dict[str, int]:
        counts = {s.value: 0 for s in Severity}
        for f in self.findings:
            counts[f.severity.value] += 1
        return counts

    @property
    def counts_by_linter(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for f in self.findings:
            counts[f.linter] = counts.get(f.linter, 0) + 1
        return counts

    def findings_for_file(self, filename: str) -> List[Finding]:
        return [f for f in self.findings if f.file == filename]

    def to_dict(self) -> dict:
        return {
            "files_analyzed": self.files_analyzed,
            "files_skipped": self.files_skipped,
            "findings": [f.to_dict() for f in self.findings],
            "results": [r.to_dict() for r in self.results],
            "counts_by_severity": self.counts_by_severity,
            "counts_by_linter": self.counts_by_linter,
            "errors": self.errors,
        }


def _common_root(files: Iterable[str]) -> str:
    """Return the nearest common ancestor directory of all files.

    Falls back to the CWD when paths share no common ancestor (e.g. a
    mix of drive letters on Windows).
    """
    abs_paths = [os.path.abspath(f) for f in files]
    try:
        common = os.path.commonpath(abs_paths)
    except ValueError:
        return os.getcwd()
    if os.path.isdir(common):
        return common
    return os.path.dirname(common)


def _group_by_extension(files: Iterable[str]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {}
    for f in files:
        suffix = Path(f).suffix.lower()
        grouped.setdefault(suffix, []).append(f)
    return grouped


def _relative(path: str, cwd: Optional[str]) -> str:
    if cwd is None:
        return path.replace(os.sep, "/")
    if os.path.isabs(path):
        try:
            return os.path.relpath(path, cwd).replace(os.sep, "/")
        except ValueError:
            pass
    return path.replace(os.sep, "/")


def analyze_files(
    files: Iterable[str],
    registry: Optional[LinterRegistry] = None,
    cwd: Optional[str] = None,
) -> AnalysisReport:
    """Run all applicable linters against the given files.

    Args:
        files: Paths to analyze (absolute or relative to *cwd*).
        registry: Optional linter registry. Defaults to the bundled one.
        cwd: Directory from which subprocesses run and to which findings
            are relativized. Defaults to the current working directory.
    """
    if registry is None:
        registry = default_registry()

    file_list = list(dict.fromkeys(files))  # dedupe, preserve order
    if not file_list:
        return AnalysisReport()

    root = cwd or _common_root(file_list)
    abs_files = [
        str(Path(f)) if os.path.isabs(f) else str(Path(root) / f)
        for f in file_list
    ]

    report = AnalysisReport()
    grouped = _group_by_extension(file_list)
    report.files_analyzed = list(file_list)
    report.files_skipped = [
        f for f in file_list if Path(f).suffix.lower() not in _SUPPORTED_EXTENSIONS
    ]

    linters = registry.linters_for_files(file_list)
    for linter in linters:
        applicable = [
            Path(abs_path).as_posix()
            for f, abs_path in zip(file_list, abs_files)
            if linter in registry.linters_for_file(f)
        ]
        if not applicable:
            continue
        if not linter.is_available():
            report.results.append(
                LintRunResult(linter=linter.name, skipped=True)
            )
            continue

        result = linter.run(applicable, cwd=root)
        result.findings = [
            f
            for f in result.findings
            if any(
                _normalized_match(f.file, abs_path)
                or _normalized_match(f.file, _relative(abs_path, root))
                for abs_path in applicable
            )
        ]
        # Relativize finding paths to the invocation root.
        for f in result.findings:
            f.file = _relative(f.file, root)
        report.findings.extend(result.findings)
        report.results.append(result)

    return report


def _normalized_match(a: str, b: str) -> bool:
    """True when two file paths refer to the same file (case/sep tolerant)."""
    return _canonical(a) == _canonical(b)


def _canonical(path: str) -> str:
    """Return a canonical, comparable form of a filesystem path.

    Resolves relative paths, normalizes case/separators, and expands
    8.3 short paths (e.g. ``AMMARS~1``) that Windows tools may emit.
    """
    try:
        expanded = os.path.abspath(os.path.expanduser(path))
        if os.name == "nt":
            expanded = _get_long_path(expanded)
        return os.path.normcase(os.path.normpath(expanded))
    except Exception:
        return os.path.normcase(os.path.normpath(path))


def _get_long_path(path: str) -> str:
    """Resolve a Windows short (8.3) path to its long form."""
    if os.name != "nt":
        return path
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(4096)
        if ctypes.windll.kernel32.GetLongPathNameW(path, buf, 4096):
            return buf.value
    except Exception:
        pass
    return path


def analyze_repo(
    repo_path: str,
    registry: Optional[LinterRegistry] = None,
    include: Optional[Iterable[str]] = None,
    exclude: Optional[Iterable[str]] = None,
) -> AnalysisReport:
    """Walk a repository and analyze every supported source file.

    Args:
        repo_path: Root of the repository to scan.
        include: Sub-path prefixes to restrict the scan to (e.g.
            {"src"}). Defaults to scanning everything.
        exclude: Sub-path prefixes to skip (e.g. {"venv", "node_modules",
            "tests"}).
    """
    root = Path(repo_path).resolve()
    exclude_set = set(exclude or ()) | {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "build",
        "dist",
        ".mypy_cache",
        ".ruff_cache",
        "target",
    }
    include_prefixes = list(include or ())

    files: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude_set]
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if Path(name).suffix.lower() not in _SUPPORTED_EXTENSIONS:
                continue
            if include_prefixes and not any(
                _startswith_path(rel, p) for p in include_prefixes
            ):
                continue
            files.append(rel)

    return analyze_files(files, registry=registry, cwd=str(root))


def _startswith_path(path: str, prefix: str) -> bool:
    try:
        return os.path.normcase(os.path.normpath(path)).startswith(
            os.path.normcase(prefix)
        )
    except Exception:
        return path.startswith(prefix)
