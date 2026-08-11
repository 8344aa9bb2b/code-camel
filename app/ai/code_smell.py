from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..analysis.finding import Severity
from ..analysis.pipeline import AnalysisReport
from .client import LLMClient, LLMClientError


@dataclass
class RefactorSuggestion:
    """An AI-generated, actionable refactor hint."""

    file: str
    message: str
    severity: Severity
    line: int | None = None
    suggestion: str | None = None
    reason: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "severity": self.severity.value,
            "suggestion": self.suggestion,
            "reason": self.reason,
        }


_SYSTEM_PROMPT = (
    "You are an expert code reviewer. Given linter findings and the relevant "
    "source snippets for a pull request, produce a focused list of actionable "
    "code-smell / refactor suggestions.\n"
    "Rules:\n"
    "- Only suggest real improvements; do not repeat the linter findings verbatim.\n"
    "- Assign one of: critical, error, warning, suggestion.\n"
    "- For each suggestion include a concrete fix or refactor direction.\n"
    '- Respond with ONLY a JSON object shaped like: '
    '{"suggestions": [{"file": "...", "line": 12, "message": "...", '
    '"severity": "warning", "suggestion": "...", "reason": "..."}]}.'
)


def build_prompt(report: AnalysisReport, snippets: Dict[str, str]) -> List[Dict[str, str]]:
    """Construct the chat messages for the model."""
    finding_lines = []
    for f in report.findings[:50]:
        loc = f"{f.file}:{f.line or '-'}"
        finding_lines.append(f"- [{f.severity.value}] {loc} {f.linter}/{f.rule}: {f.message}")

    snippet_lines = []
    for path, code in list(snippets.items())[:20]:
        snippet_lines.append(f"```{path}\n{code}\n```")

    findings_block = "\n".join(finding_lines) or "No linter findings."
    snippets_block = "\n\n".join(snippet_lines) or "No source snippets."

    user = (
        f"## Linter findings\n{findings_block}\n\n"
        f"## Source snippets\n{snippets_block}"
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _extract_json(text: str) -> Any:
    """Parse the JSON object out of the model's reply (tolerating fences)."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _severity(value: Any) -> Severity:
    try:
        return Severity(str(value).lower())
    except ValueError:
        return Severity.SUGGESTION


def parse_response(text: str) -> List[RefactorSuggestion]:
    """Convert the model's JSON reply into refactor suggestions."""
    try:
        data = _extract_json(text)
    except json.JSONDecodeError as exc:
        raise LLMClientError(f"Could not parse LLM JSON response: {exc}") from exc

    items = data.get("suggestions", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        raise LLMClientError("LLM response is not a list of suggestions.")

    suggestions: List[RefactorSuggestion] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("message"):
            continue
        suggestions.append(
            RefactorSuggestion(
                file=str(item.get("file", "")),
                line=item.get("line"),
                message=str(item["message"]),
                severity=_severity(item.get("severity")),
                suggestion=str(item.get("suggestion", "")) or None,
                reason=str(item.get("reason", "")) or None,
            )
        )
    return suggestions


def generate_refactor_suggestions(
    report: AnalysisReport,
    snippets: Dict[str, str],
    client: Optional[LLMClient] = None,
) -> List[RefactorSuggestion]:
    """Run the AI code-smell pass over *report* findings + *snippets*."""
    client = client or LLMClient()
    messages = build_prompt(report, snippets)
    text = client.complete(messages)
    return parse_response(text)
