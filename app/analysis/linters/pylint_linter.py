from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from ..base import Linter
from ..finding import Finding, LintRunResult, Severity

# Map pylint category -> normalized severity.
_CATEGORY_TO_SEVERITY = {
    "fatal": Severity.CRITICAL,
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "refactor": Severity.SUGGESTION,
    "convention": Severity.SUGGESTION,
}


class PylintLinter(Linter):
    """Runs Pylint on Python source files and parses JSON output."""

    name = "pylint"
    description = "Pylint - Python static analysis (errors, warnings, style)"
    extensions = frozenset({".py"})

    def __init__(self, pylint_cmd: Optional[str] = None, timeout: int = 120):
        self._pylint_cmd = pylint_cmd or os.getenv("PYLINT_CMD") or "pylint"
        self.timeout = timeout

    def _command_prefix(self) -> List[str]:
        cmd = self._pylint_cmd
        if cmd in ("pylint", None, ""):
            return [sys.executable, "-m", "pylint"]
        return cmd.split()

    def is_available(self) -> bool:
        prefix = self._command_prefix()
        if prefix[0] == sys.executable:
            # python -m pylint -> check module importable
            probe = subprocess.run(
                [sys.executable, "-m", "pylint", "--version"],
                capture_output=True,
                timeout=self.timeout,
            )
            return probe.returncode == 0
        return shutil.which(prefix[0]) is not None

    def run(
        self, files: list[str], cwd: Optional[str] = None
    ) -> LintRunResult:
        if not files:
            return LintRunResult(linter=self.name)

        cmd = self._command_prefix() + [
            "--output-format=json",
            "--reports=no",
            "--score=no",
        ] + files

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=cwd,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return LintRunResult(
                linter=self.name,
                errors=[f"failed to run pylint: {exc}"],
            )

        if proc.returncode & 32:
            # Bitmask flag 32 -> usage error (bad args). Other bits
            # (2=errors, 4=warnings, 8=refactor, 16=convention) simply mean
            # findings were emitted, so those are parsed normally.
            return LintRunResult(
                linter=self.name,
                errors=[
                    proc.stderr.strip()
                    or f"pylint exited with code {proc.returncode}"
                ],
            )

        return self._parse(proc.stdout)

    def _parse(self, raw: str) -> LintRunResult:
        result = LintRunResult(linter=self.name)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            result.errors.append(
                f"pylint returned non-JSON output: {raw[:200]}"
            )
            return result

        for item in payload:
            severity = _CATEGORY_TO_SEVERITY.get(
                item.get("type"), Severity.WARNING
            )
            result.findings.append(
                Finding(
                    linter=self.name,
                    rule=item.get("symbol") or item.get("message-id", "?"),
                    message=item.get("message", ""),
                    severity=severity,
                    file=item.get("path", ""),
                    line=item.get("line"),
                    column=(item.get("column") or 0) + 1,
                    end_line=item.get("endLine"),
                    end_column=(
                        (item.get("endColumn") or 0) + 1
                        if item.get("endColumn") is not None
                        else None
                    ),
                )
            )
        return result

    def lint_string(self, content: str, filename: str) -> LintRunResult:
        suffix = Path(filename).suffix or ".py"
        with tempfile.NamedTemporaryFile(
            "w", suffix=suffix, delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            return self.run([tmp_path])
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
