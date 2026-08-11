from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .base import Linter
from .linters import (
    BanditLinter,
    CheckstyleLinter,
    ESLintLinter,
    PylintLinter,
    SpotBugsLinter,
)


class LinterRegistry:
    """Maps file extensions to the linters that can analyze them."""

    def __init__(self):
        self._linters: List[Linter] = []
        self._by_extension: Dict[str, List[Linter]] = {}

    def register(self, linter: Linter) -> None:
        if not isinstance(linter, Linter):
            raise TypeError(f"expected a Linter, got {type(linter)}")
        self._linters.append(linter)
        for ext in linter.extensions:
            self._by_extension.setdefault(ext, []).append(linter)

    def linters_for_file(self, filename: str) -> List[Linter]:
        suffix = Path(filename).suffix.lower()
        return list(self._by_extension.get(suffix, []))

    def linters_for_files(self, files: Iterable[str]) -> List[Linter]:
        ordered: List[Linter] = []
        seen = set()
        for f in files:
            for linter in self.linters_for_file(f):
                if linter.name not in seen:
                    seen.add(linter.name)
                    ordered.append(linter)
        return ordered

    @property
    def all(self) -> List[Linter]:
        return list(self._linters)

    def available(self) -> List[Linter]:
        return [l for l in self._linters if l.is_available()]


def default_registry(
    pylint_cmd: Optional[str] = None,
    eslint_cmd: Optional[str] = None,
    checkstyle_jar: Optional[str] = None,
    checkstyle_config: Optional[str] = None,
    bandit_cmd: Optional[str] = None,
    spotbugs_jar: Optional[str] = None,
    timeout: int = 120,
) -> LinterRegistry:
    """Build a registry with the bundled linters."""
    registry = LinterRegistry()
    registry.register(PylintLinter(pylint_cmd=pylint_cmd, timeout=timeout))
    registry.register(BanditLinter(bandit_cmd=bandit_cmd, timeout=timeout))
    registry.register(ESLintLinter(eslint_cmd=eslint_cmd, timeout=timeout))
    registry.register(
        CheckstyleLinter(
            jar=checkstyle_jar,
            config=checkstyle_config,
            timeout=timeout,
        )
    )
    registry.register(SpotBugsLinter(jar=spotbugs_jar, timeout=timeout))
    return registry


def app_registry() -> LinterRegistry:
    """Build the registry from the Flask app configuration."""
    from .. import config

    return default_registry(
        pylint_cmd=config.PYLINT_CMD,
        eslint_cmd=config.ESLINT_CMD,
        checkstyle_jar=config.CHECKSTYLE_JAR,
        checkstyle_config=config.CHECKSTYLE_CONFIG,
        bandit_cmd=config.BANDIT_CMD,
        spotbugs_jar=config.SPOTBUGS_JAR,
        timeout=config.LINTER_TIMEOUT,
    )
