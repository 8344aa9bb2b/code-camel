from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

from ..base import Linter
from ..finding import Finding, LintRunResult, Severity

# SpotBugs priority (1=High, 2=Normal, 3=Low) -> normalized severity.
_SPOTBUGS_PRIORITY = {
    "1": Severity.ERROR,
    "2": Severity.WARNING,
    "3": Severity.SUGGESTION,
}


class SpotBugsLinter(Linter):
    """Runs SpotBugs on Java bytecode and parses the XML report.

    SpotBugs analyzes compiled classes (not source), so this linter
    first compiles the Java files with ``javac`` into a temporary
    directory and then runs the SpotBugs CLI against the classes.
    """

    name = "spotbugs"
    description = "SpotBugs - Java bug-pattern detection (bytecode analysis)"
    extensions = frozenset({".java"})

    def __init__(
        self,
        jar: Optional[str] = None,
        java_cmd: Optional[str] = None,
        javac_cmd: Optional[str] = None,
        timeout: int = 120,
    ):
        self.jar = jar or os.getenv("SPOTBUGS_JAR", "spotbugs.jar")
        self.java_cmd = java_cmd or os.getenv("JAVA_CMD", "java")
        self.javac_cmd = javac_cmd or os.getenv("JAVAC_CMD", "javac")
        self.timeout = timeout

    def is_available(self) -> bool:
        if not Path(self.jar).is_file() and shutil.which(self.jar) is None:
            return False
        return (
            shutil.which(self.java_cmd) is not None
            and shutil.which(self.javac_cmd) is not None
        )

    def run(
        self, files: list[str], cwd: Optional[str] = None
    ) -> LintRunResult:
        if not files:
            return LintRunResult(linter=self.name)

        with tempfile.TemporaryDirectory(prefix="spotbugs-") as tmp:
            classes_dir = os.path.join(tmp, "classes")
            os.makedirs(classes_dir, exist_ok=True)

            compile_errors = self._compile(files, classes_dir, cwd)
            if compile_errors:
                return LintRunResult(linter=self.name, errors=compile_errors)

            report_xml = os.path.join(tmp, "report.xml")
            analysis_errors = self._analyze(classes_dir, report_xml, cwd)
            if analysis_errors:
                return LintRunResult(linter=self.name, errors=analysis_errors)

            result = self._parse_xml(report_xml)
            self._remap_files(result, files)
            return result

    def _compile(
        self, files: list[str], classes_dir: str, cwd: Optional[str]
    ) -> List[str]:
        """Compile Java sources. Returns a list of error messages."""
        cmd = [self.javac_cmd, "-d", classes_dir] + files
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=cwd,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return [f"failed to run javac: {exc}"]

        if proc.returncode != 0:
            stderr = (proc.stderr or proc.stdout or "").strip()
            if stderr:
                # Keep it short: first line is usually the actual error.
                first = stderr.splitlines()[0]
                return [
                    f"spotbugs could not compile the Java sources: {first}"
                ]
            return [f"javac exited with code {proc.returncode}"]
        return []

    def _analyze(
        self, classes_dir: str, report_xml: str, cwd: Optional[str]
    ) -> List[str]:
        """Run SpotBugs against the compiled classes."""
        cmd = [
            self.java_cmd,
            "-jar",
            self.jar,
            "-textui",
            "-xml:withMessages",
            "-output",
            report_xml,
            classes_dir,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=cwd,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return [f"failed to run spotbugs: {exc}"]

        if not os.path.isfile(report_xml):
            return [
                proc.stderr.strip()
                or proc.stdout.strip()
                or f"spotbugs exited with code {proc.returncode}"
            ]
        return []

    def _parse(self, raw: str) -> LintRunResult:
        result = LintRunResult(linter=self.name)
        try:
            root = ET.fromstring(raw)
        except (ET.ParseError, ValueError) as exc:
            result.errors.append(f"spotbugs returned invalid XML: {exc}")
            return result

        for bug in root.iter("BugInstance"):
            severity = _SPOTBUGS_PRIORITY.get(
                bug.get("priority"), Severity.WARNING
            )
            message = ""
            for child in bug:
                if child.tag == "LongMessage":
                    message = (child.text or "").strip()
                    break
            line = self._primary_line(bug)
            sourcepath = self._sourcepath(bug)
            result.findings.append(
                Finding(
                    linter=self.name,
                    rule=bug.get("type") or "?",
                    message=message or bug.get("abbrev") or "?",
                    severity=severity,
                    file=sourcepath,
                    line=line,
                )
            )
        return result

    def _parse_xml(self, report_path: str) -> LintRunResult:
        try:
            with open(report_path, "r", encoding="utf-8") as fh:
                return self._parse(fh.read())
        except OSError as exc:
            return LintRunResult(
                linter=self.name,
                errors=[f"spotbugs could not read report: {exc}"],
            )

    @staticmethod
    def _primary_line(bug: ET.Element) -> Optional[int]:
        """Find the bug's precise source line (the primary SourceLine)."""
        for el in bug.iter("SourceLine"):
            if el.get("primary") == "true" or el.get("role"):
                value = el.get("start")
                if value:
                    return int(value)
        # Fall back to any line info we can find.
        for el in bug.iter("SourceLine"):
            value = el.get("start")
            if value:
                return int(value)
        return None

    @staticmethod
    def _sourcepath(bug: ET.Element) -> str:
        for el in bug.iter("SourceLine"):
            if el.get("primary") == "true":
                return el.get("sourcepath") or el.get("sourcefile") or ""
        for el in bug.iter("SourceLine"):
            if el.get("sourcepath"):
                return el.get("sourcepath") or ""
        return ""

    @staticmethod
    def _remap_files(result: LintRunResult, files: list[str]) -> None:
        """Map SpotBugs' basename-only paths back to the requested files.

        javac embeds only the source filename in the class file, so the
        report contains basenames. Reattach the full requested path when
        there is a unique match.
        """
        by_basename: Dict[str, List[str]] = {}
        for f in files:
            by_basename.setdefault(os.path.basename(f), []).append(f)

        for finding in result.findings:
            matches = by_basename.get(os.path.basename(finding.file), [])
            if len(matches) == 1:
                finding.file = matches[0]

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
