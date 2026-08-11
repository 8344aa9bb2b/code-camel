import json
import os
import subprocess
import sys

import pytest

from app.analysis.pipeline import analyze_repo
from app.analysis.registry import default_registry


def _run_cli(args, cwd=None):
    codebase = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return subprocess.run(
        [sys.executable, "-m", "app.analysis.cli"] + args,
        capture_output=True,
        text=True,
        timeout=180,
        cwd=cwd or codebase,
    )


@pytest.mark.integration
class TestCLIIntegration:
    def test_cli_pylint_finds_real_issues(self, tmp_path):
        sample = tmp_path / "demo.py"
        sample.write_text(
            "import os\nimport sys\n\n"
            "def broken():\n"
            "    return undefined_var\n",
            encoding="utf-8",
        )
        proc = _run_cli(["--json", str(sample)])
        assert proc.returncode == 0, proc.stderr

        report = json.loads(proc.stdout)
        linters = {r["linter"]: r for r in report["results"]}
        assert "pylint" in linters
        assert not linters["pylint"]["skipped"]

        findings = report["findings"]
        assert findings, "expected pylint to flag the broken demo file"
        assert all(f["linter"] == "pylint" for f in findings)
        # undefined-variable is a real, language-level finding
        rules = {f["rule"] for f in findings}
        assert "undefined-variable" in rules

    def test_cli_repo_scan(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src").joinpath("demo.py").write_text(
            "import os\n\nx = 1\n", encoding="utf-8"
        )
        proc = _run_cli(["--json", str(tmp_path)])
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        assert report["files_analyzed"] == ["src/demo.py"]

    def test_cli_eslint_finds_real_issues(self, tmp_path):
        sample = tmp_path / "demo.js"
        sample.write_text(
            "const unused = 1;\nfunction f() { return unused; }\n",
            encoding="utf-8",
        )
        proc = _run_cli(["--json", str(sample)])
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        linters = {r["linter"]: r for r in report["results"]}
        if linters.get("eslint", {}).get("skipped", True):
            pytest.skip("eslint not installed")
        assert any(f["rule"] == "no-unused-vars" for f in report["findings"])

    def test_cli_checkstyle_finds_real_issues(self, tmp_path):
        jar = os.getenv("CHECKSTYLE_JAR")
        if not jar or not os.path.isfile(jar):
            pytest.skip("CHECKSTYLE_JAR not set")
        sample = tmp_path / "Demo.java"
        sample.write_text(
            "public class Demo {\n  int _bad = 1;\n  int magic = 42;\n}\n",
            encoding="utf-8",
        )
        proc = _run_cli(["--json", "--checkstyle-jar", jar, str(sample)])
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        linters = {r["linter"]: r for r in report["results"]}
        if linters.get("checkstyle", {}).get("skipped", True):
            pytest.skip("checkstyle unavailable")
        assert report["findings"]

    def test_cli_bandit_finds_real_issues(self, tmp_path):
        sample = tmp_path / "demo.py"
        sample.write_text(
            "import subprocess\n"
            "def run(cmd):\n"
            "    return subprocess.Popen(cmd, shell=True)\n",
            encoding="utf-8",
        )
        proc = _run_cli(["--json", str(sample)])
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        linters = {r["linter"]: r for r in report["results"]}
        if linters.get("bandit", {}).get("skipped", True):
            pytest.skip("bandit not installed")
        # B602 is the shell=True injection pattern.
        assert any(
            f["rule"] == "B602" for f in report["findings"]
        ), f"expected B602, got {[f['rule'] for f in report['findings']]}"

    def test_cli_spotbugs_finds_real_issues(self, tmp_path):
        jar = os.getenv("SPOTBUGS_JAR")
        if not jar or not os.path.isfile(jar):
            pytest.skip("SPOTBUGS_JAR not set")
        sample = tmp_path / "Demo.java"
        sample.write_text(
            "public class Demo {\n"
            "    public int divide(int a, int b) {\n"
            "        return a / b;\n"
            "    }\n"
            "    public static void main(String[] args) {\n"
            "        Demo d = new Demo();\n"
            "        System.out.println(d.divide(10, 0));\n"
            "        String s = null;\n"
            "        System.out.println(s.length());\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        proc = _run_cli(["--json", "--spotbugs-jar", jar, str(sample)])
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        linters = {r["linter"]: r for r in report["results"]}
        if linters.get("spotbugs", {}).get("skipped", True):
            pytest.skip("spotbugs unavailable")
        # NP_ALWAYS_NULL is the null-dereference pattern on line 9.
        assert any(
            f["rule"] == "NP_ALWAYS_NULL" for f in report["findings"]
        ), f"expected NP_ALWAYS_NULL, got {[f['rule'] for f in report['findings']]}"
