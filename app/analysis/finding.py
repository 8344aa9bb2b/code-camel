from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class Severity(str, Enum):
    """Normalized severity levels across all linters."""

    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    SUGGESTION = "suggestion"


@dataclass
class Finding:
    """A single normalized issue detected by a linter."""

    linter: str
    rule: str
    message: str
    severity: Severity
    file: str
    line: int | None = None
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None
    code: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "linter": self.linter,
            "rule": self.rule,
            "message": self.message,
            "severity": self.severity.value,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
            "code": self.code,
        }

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"Finding({self.severity.value}:{self.file}:{self.line} "
            f"{self.linter}/{self.rule}: {self.message})"
        )


@dataclass
class LintRunResult:
    """Outcome of running a single linter."""

    linter: str
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors and not self.skipped

    def to_dict(self) -> Dict[str, Any]:
        return {
            "linter": self.linter,
            "findings": [f.to_dict() for f in self.findings],
            "errors": self.errors,
            "skipped": self.skipped,
        }
