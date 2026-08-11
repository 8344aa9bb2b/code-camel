from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .pipeline import analyze_files, analyze_repo
from .registry import default_registry


def _resolve_paths(paths: List[str]) -> tuple[Optional[str], List[str]]:
    """Split CLI paths into a repo root (if a dir) and file list."""
    if not paths:
        return None, []
    if len(paths) == 1 and Path(paths[0]).is_dir():
        return paths[0], []
    root = None
    files = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            root = str(path)
        else:
            files.append(str(path))
    return root, files


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="code-review-agent",
        description="Run the bundled linters over files or a repository.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files to analyze, or a single directory to scan.",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="Sub-path prefix to scan (repeatable, directory mode).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Sub-path prefix to skip (repeatable, directory mode).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    parser.add_argument(
        "--pylint-cmd",
        default=None,
        help="Override the pylint command.",
    )
    parser.add_argument(
        "--eslint-cmd",
        default=None,
        help="Override the eslint command (or 'npx eslint').",
    )
    parser.add_argument(
        "--checkstyle-jar",
        default=None,
        help="Path to the checkstyle.jar.",
    )
    parser.add_argument(
        "--checkstyle-config",
        default=None,
        help="Path to a Checkstyle XML config.",
    )
    parser.add_argument(
        "--bandit-cmd",
        default=None,
        help="Override the bandit command.",
    )
    parser.add_argument(
        "--spotbugs-jar",
        default=None,
        help="Path to the spotbugs.jar.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-linter subprocess timeout in seconds.",
    )
    args = parser.parse_args(argv)

    registry = default_registry(
        pylint_cmd=args.pylint_cmd,
        eslint_cmd=args.eslint_cmd,
        checkstyle_jar=args.checkstyle_jar,
        checkstyle_config=args.checkstyle_config,
        bandit_cmd=args.bandit_cmd,
        spotbugs_jar=args.spotbugs_jar,
        timeout=args.timeout,
    )

    root, files = _resolve_paths(args.paths)
    if root is not None:
        report = analyze_repo(
            root,
            registry=registry,
            include=args.include or None,
            exclude=args.exclude or None,
        )
    else:
        report = analyze_files(files, registry=registry)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0

    print(f"Analyzed {len(report.files_analyzed)} files, "
          f"skipped {len(report.files_skipped)}.")
    for linter_result in report.results:
        status = (
            "skipped (not installed)"
            if linter_result.skipped
            else f"{len(linter_result.findings)} findings"
        )
        print(f"  [{linter_result.linter}] {status}")
        for e in linter_result.errors:
            print(f"    ERROR: {e}")

    if not report.findings:
        print("\nNo findings. Clean code!")
        return 0

    print("\nFindings:")
    for f in report.findings:
        loc = f"{f.file}:{f.line or 0}:{f.column or 0}"
        print(f"  [{f.severity.value:<10}] {loc} {f.linter}/{f.rule} - {f.message}")

    total = sum(report.counts_by_severity.values())
    counts = ", ".join(f"{k}={v}" for k, v in report.counts_by_severity.items() if v)
    print(f"\n{total} finding(s) total ({counts}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
