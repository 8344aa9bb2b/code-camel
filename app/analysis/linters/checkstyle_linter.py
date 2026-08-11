from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

from ..base import Linter
from ..finding import Finding, LintRunResult, Severity

_CHECKSTYLE_SEVERITY = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "info": Severity.SUGGESTION,
    "ignore": Severity.SUGGESTION,
}

_DEFAULT_CONFIG = Path(__file__).with_name("checkstyle_config.xml")


class CheckstyleLinter(Linter):
    """Runs Checkstyle on Java source files."""

    name = "checkstyle"
    description = "Checkstyle - Java coding standard enforcement"
    extensions = frozenset({".java"})

    def __init__(
        self,
        jar: Optional[str] = None,
        config: Optional[str] = None,
        java_cmd: Optional[str] = None,
        timeout: int = 120,
    ):
        self.jar = jar or os.getenv("CHECKSTYLE_JAR", "checkstyle.jar")
        self.config = config or os.getenv(
            "CHECKSTYLE_CONFIG", str(_DEFAULT_CONFIG)
        )
        self.java_cmd = java_cmd or os.getenv("JAVA_CMD", "java")
        self.timeout = timeout

    def is_available(self) -> bool:
        if not Path(self.jar).is_file() and shutil.which(self.jar) is None:
            return False
        return shutil.which(self.java_cmd) is not None

    def run(
        self, files: list[str], cwd: Optional[str] = None
    ) -> LintRunResult:
        if not files:
            return LintRunResult(linter=self.name)

        cmd = [
            self.java_cmd,
            "-jar",
            self.jar,
            "-c",
            self.config,
            "-f",
            "xml",
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
                linter=self.name, errors=[f"failed to run checkstyle: {exc}"]
            )

        if proc.returncode not in (0, 1, 2):
            return LintRunResult(
                linter=self.name,
                errors=[
                    proc.stderr.strip()
                    or f"checkstyle exited with code {proc.returncode}"
                ],
            )

        return self._parse(proc.stdout)

    def _parse(self, raw: str) -> LintRunResult:
        result = LintRunResult(linter=self.name)
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            result.errors.append(
                f"checkstyle returned invalid XML: {raw[:200]}"
            )
            return result

        for file_el in root.iter("file"):
            file_name = file_el.get("name", "")
            for err in file_el.iter("error"):
                rule = (err.get("source") or "?").rsplit(".", 1)[-1]
                result.findings.append(
                    Finding(
                        linter=self.name,
                        rule=rule,
                        message=err.get("message", ""),
                        severity=_CHECKSTYLE_SEVERITY.get(
                            err.get("severity", "warning"),
                            Severity.WARNING,
                        ),
                        file=file_name,
                        line=int(err.get("line") or 0) or None,
                        column=int(err.get("column") or 0) or None,
                    )
                )
        return result

    def lint_string(self, content: str, filename: str) -> LintRunResult:
        suffix = Path(filename).suffix or ".java"
        with tempfile.NamedTemporaryFile(
            "w", suffix=suffix, delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            return self.run([tmp_path], cwd=os.path.dirname(tmp_path))
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
