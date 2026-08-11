from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict, List

from .analysis.pipeline import AnalysisReport, _SUPPORTED_EXTENSIONS, analyze_files
from .analysis.registry import app_registry
from .github_client import GitHubClient


def _changed_files(files: List[Dict]) -> List[Dict]:
    """Keep only files whose content exists at the head SHA."""
    return [f for f in files if f.get("status") != "removed"]


def _supported_files(files: List[Dict]) -> List[Dict]:
    return [
        f for f in files if Path(f["filename"]).suffix.lower() in _SUPPORTED_EXTENSIONS
    ]


def _download_contents(
    owner: str, repo: str, files: List[Dict], ref: str, dest: Path, client: GitHubClient
) -> List[str]:
    paths: List[str] = []
    for f in files:
        target = dest / f["filename"]
        target.parent.mkdir(parents=True, exist_ok=True)
        content = client.fetch_file_content(owner, repo, f["filename"], ref)
        target.write_bytes(content)
        paths.append(str(target))
    return paths


def build_summary(report: AnalysisReport) -> str:
    """Render an analysis report as a Markdown PR comment."""
    lines = ["## Code Review Agent"]

    counts = report.counts_by_severity
    if not report.findings:
        lines.append("No issues found. Clean code! :rocket:")
        return "\n".join(lines)

    total = len(report.findings)
    parts = ", ".join(f"{k}: {v}" for k, v in counts.items() if v)
    lines.append(f"Found **{total}** finding(s) across {len(report.files_analyzed)} file(s).")
    lines.append(f"Severity breakdown: {parts}.")
    lines.append("")
    lines.append("| File | Line | Linter / Rule | Severity | Message |")
    lines.append("| --- | --- | --- | --- | --- |")
    for f in report.findings:
        line = str(f.line) if f.line is not None else "-"
        message = f.message.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {f.file} | {line} | {f.linter} / {f.rule} | {f.severity.value} | {message} |")

    skipped = [r.linter for r in report.results if r.skipped]
    if skipped:
        lines.append("")
        lines.append(f"*(Linters skipped: {', '.join(sorted(skipped))} — not installed.)*")

    return "\n".join(lines)


def review_pull_request(
    owner: str,
    repo: str,
    pr_number: int,
    head_sha: str,
    client: GitHubClient | None = None,
) -> AnalysisReport:
    """Analyze a PR's changed files and post a summary comment."""
    client = client or GitHubClient()
    files = _changed_files(client.list_pr_files(owner, repo, pr_number))
    files = _supported_files(files)

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        paths = _download_contents(owner, repo, files, head_sha, dest, client)
        report = analyze_files(paths, registry=app_registry(), cwd=str(dest))

    body = build_summary(report)
    client.post_comment(owner, repo, pr_number, body)
    return report
