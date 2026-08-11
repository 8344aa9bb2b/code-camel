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

# Bandit issue_severity -> normalized severity.
_BANDIT_SEVERITY = {
    "HIGH": Severity.ERROR,
    "MEDIUM": Severity.WARNING,
    "LOW": Severity.SUGGESTION,
}

# Bandit exit codes: 0 = clean, 1 = findings emitted, 2 = internal error.
_BANDIT_ERROR_EXIT = 2


class BanditLinter(Linter):
    """Runs Bandit on Python source files and parses JSON output.

    Bandit is a security-focused static analyzer that detects common
    vulnerability patterns (shell injection, hardcoded secrets, unsafe
    imports, XML/deserialization risks, etc.).
    """

    name = "bandit"
    description = "Bandit - Python security/bug-pattern detection"
    extensions = frozenset({".py"})

    def __init__(
        self, bandit_cmd: Optional[str] = None, timeout: int = 120
    ):
        self._bandit_cmd = bandit_cmd or os.getenv("BANDIT_CMD") or "bandit"
        self.timeout = timeout

    def _command_prefix(self) -> List[str]:
        cmd = self._bandit_cmd
        if cmd in ("bandit", None, ""):
            return [sys.executable, "-m", "bandit"]
        return cmd.split()

    def is_available(self) -> bool:
        prefix = self._command_prefix()
        if prefix[0] == sys.executable:
            # python -m bandit -> check module importable
            probe = subprocess.run(
                [sys.executable, "-m", "bandit", "--version"],
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
            "-q",  # reduce console noise
            "-f", "json",
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
                linter=self.name, errors=[f"failed to run bandit: {exc}"]
            )

        if proc.returncode == _BANDIT_ERROR_EXIT:
            # Internal bandit failure (e.g. unparseable file). Exit code 1
            # simply means "findings were emitted", so that is parsed
            # normally rather than treated as an error.
            return LintRunResult(
                linter=self.name,
                errors=[
                    proc.stderr.strip()
                    or f"bandit exited with code {proc.returncode}"
                ],
            )

        return self._parse(proc.stdout, proc.returncode)

    def _parse(self, raw: str, returncode: int = 0) -> LintRunResult:
        result = LintRunResult(linter=self.name)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            # bandit emitted no JSON (no findings with -q, or failure).
            if returncode == 0:
                return result
            result.errors.append(f"bandit returned non-JSON output: {raw[:200]}")
            return result

        for error in payload.get("errors", []):
            result.errors.append(
                f"bandit error on {error.get('filename', '?')}: "
                f"{error.get('reason', error)}"
            )

        for item in payload.get("results", []):
            severity = _BANDIT_SEVERITY.get(
                item.get("issue_severity", "LOW"), Severity.SUGGESTION
            )
            result.findings.append(
                Finding(
                    linter=self.name,
                    rule=item.get("test_id") or item.get("test_name", "?"),
                    message=item.get("issue_text", ""),
                    severity=severity,
                    file=item.get("filename", ""),
                    line=item.get("line_number"),
                    column=(item.get("col_offset") or 0) + 1,
                    end_column=(
                        (item.get("end_col_offset") or 0) + 1
                        if item.get("end_col_offset") is not None
                        else None
                    ),
                    code=item.get("code"),
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
