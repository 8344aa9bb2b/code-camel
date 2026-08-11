from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from ..base import Linter
from ..finding import Finding, LintRunResult, Severity

# Minimal flat config used when a project ships no ESLint config.
# Self-contained (no external imports) so it works from any location.
# A curated subset of eslint:recommended plus universal safety rules.
_FALLBACK_CONFIG = """\
export default [
  {
    files: ["**/*.{js,mjs,cjs}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        console: "readonly",
        process: "readonly",
        module: "readonly",
        require: "readonly",
        __dirname: "readonly",
        window: "readonly",
        document: "readonly",
        fetch: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
      },
    },
    rules: {
      "no-undef": "error",
      "no-unused-vars": "warn",
      "no-debugger": "warn",
      "no-dupe-keys": "error",
      "no-duplicate-case": "error",
      "no-extra-semi": "error",
      "no-redeclare": "error",
      "no-unreachable": "error",
      "no-constant-condition": "warn",
      "no-cond-assign": "error",
      "no-func-assign": "error",
      "no-fallthrough": "error",
      "no-obj-calls": "error",
      "no-sparse-arrays": "error",
      "no-unexpected-multiline": "error",
      "valid-typeof": "error",
    },
  },
];
"""

# ESLint numeric severity -> normalized severity.
_NUM_TO_SEVERITY = {
    2: Severity.ERROR,
    1: Severity.WARNING,
    0: Severity.SUGGESTION,
}


class ESLintLinter(Linter):
    """Runs ESLint on JavaScript/TypeScript source files."""

    name = "eslint"
    description = "ESLint - JavaScript/TypeScript static analysis"
    extensions = frozenset(
        {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
    )

    def __init__(self, eslint_cmd: Optional[str] = None, timeout: int = 120):
        self._eslint_cmd = (
            eslint_cmd or os.getenv("ESLINT_CMD") or "eslint"
        )
        self.timeout = timeout

    def _command(self) -> List[str]:
        cmd = self._eslint_cmd.split()
        if cmd and cmd[0] != "npx":
            resolved = shutil.which(cmd[0])
            if resolved:
                cmd = [resolved] + cmd[1:]
        return cmd

    def is_available(self) -> bool:
        cmd = self._command()
        if cmd and cmd[0] == "npx":
            # npx --no-install eslint --version
            probe = cmd + ["--no-install", "eslint", "--version"]
        else:
            probe = [cmd[0], "--version"] if cmd else []
        try:
            proc = subprocess.run(
                probe, capture_output=True, timeout=self.timeout
            )
            return proc.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    def run(
        self, files: list[str], cwd: Optional[str] = None
    ) -> LintRunResult:
        if not files:
            return LintRunResult(linter=self.name)

        cmd = self._command()
        if cmd and cmd[0] == "npx":
            cmd += ["--no-install", "eslint"]
        cmd += ["--format", "json"]

        config_path, cleanup_needed = self._resolve_config(cwd)
        if config_path:
            cmd += ["--config", config_path]
        cmd += files

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=cwd,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            if cleanup_needed and config_path:
                self._cleanup_config(config_path)
            return LintRunResult(
                linter=self.name, errors=[f"failed to run eslint: {exc}"]
            )

        if cleanup_needed and config_path:
            self._cleanup_config(config_path)

        if proc.returncode not in (0, 1):
            return LintRunResult(
                linter=self.name,
                errors=[
                    proc.stderr.strip()
                    or f"eslint exited with code {proc.returncode}"
                ],
            )

        return self._parse(proc.stdout)

    def _resolve_config(self, cwd: Optional[str]) -> tuple[Optional[str], bool]:
        """Return (config_path, cleanup_needed).

        config_path is None when ESLint will auto-discover the project
        config (i.e. cwd is not provided), or the path to a temporary
        fallback config when no project config exists. cleanup_needed is
        True only for the temporary fallback file we create.
        """
        if cwd is None:
            return None, False
        root = Path(cwd)
        candidates = [
            "eslint.config.js",
            "eslint.config.mjs",
            "eslint.config.cjs",
            ".eslintrc.js",
            ".eslintrc.cjs",
            ".eslintrc.json",
            ".eslintrc.yml",
            ".eslintrc.yaml",
        ]
        for name in candidates:
            if (root / name).is_file():
                return str(root / name), False
        # No project config: write a fallback flat config *inside cwd*.
        # ESLint uses the config file's directory as its base path, so a
        # config in a temp dir would cause every target file to be ignored.
        fallback = root / ".code-review-agent.eslint.config.mjs"
        try:
            fallback.write_text(_FALLBACK_CONFIG, encoding="utf-8")
        except OSError as exc:
            # cwd not writable; rely on ESLint auto-discovery (may still
            # fail on a config-less repo, but that is reported cleanly).
            return None, False
        return str(fallback), True

    @staticmethod
    def _cleanup_config(path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            pass

    def _parse(self, raw: str) -> LintRunResult:
        result = LintRunResult(linter=self.name)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            result.errors.append(
                f"eslint returned non-JSON output: {raw[:200]}"
            )
            return result

        for entry in payload:
            file_path = entry.get("filePath", "")
            for msg in entry.get("messages", []):
                if msg.get("ruleId") is None:
                    # Fatal parse errors have no rule id.
                    continue
                result.findings.append(
                    Finding(
                        linter=self.name,
                        rule=msg.get("ruleId", "?"),
                        message=msg.get("message", ""),
                        severity=_NUM_TO_SEVERITY.get(
                            msg.get("severity"), Severity.WARNING
                        ),
                        file=file_path,
                        line=msg.get("line"),
                        column=msg.get("column"),
                        end_line=msg.get("endLine"),
                        end_column=msg.get("endColumn"),
                    )
                )
        return result

    def lint_string(self, content: str, filename: str) -> LintRunResult:
        suffix = Path(filename).suffix or ".js"
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
