from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .finding import Finding, LintRunResult


class Linter(ABC):
    """Abstract base class for a language-specific linter wrapper."""

    #: Unique identifier for this linter.
    name: str = "linter"
    #: File extensions this linter understands (e.g. {".py"}).
    extensions: frozenset[str] = frozenset()
    #: Human readable description.
    description: str = ""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the underlying tool is installed and runnable."""

    @abstractmethod
    def run(
        self, files: list[str], cwd: Optional[str] = None
    ) -> LintRunResult:
        """Run the linter against *files* and return normalized findings."""

    @property
    def supports_stdin(self) -> bool:
        return False

    def lint_string(self, content: str, filename: str) -> LintRunResult:
        """Run the linter on in-memory content.

        Default implementation writes to a temp file; subclasses may
        override to pipe via stdin when ``supports_stdin`` is True.
        """
        raise NotImplementedError(
            f"{self.name} does not support linting raw content"
        )
