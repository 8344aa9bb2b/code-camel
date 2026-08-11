import json

import pytest

from app.analysis.finding import Severity
from app.analysis.linters.bandit_linter import BanditLinter
from app.analysis.linters.checkstyle_linter import CheckstyleLinter
from app.analysis.linters.eslint_linter import ESLintLinter
from app.analysis.linters.pylint_linter import PylintLinter
from app.analysis.linters.spotbugs_linter import SpotBugsLinter


class TestPylintParsing:
    def test_parse_json_findings(self):
        payload = [
            {
                "type": "error",
                "module": "demo",
                "obj": "foo",
                "line": 5,
                "column": 3,
                "endLine": 5,
                "endColumn": 8,
                "path": "demo.py",
                "symbol": "undefined-variable",
                "message": "Undefined variable 'x'",
                "message-id": "E0602",
            },
            {
                "type": "convention",
                "module": "demo",
                "obj": "",
                "line": 1,
                "column": 0,
                "endLine": None,
                "endColumn": None,
                "path": "demo.py",
                "symbol": "missing-module-docstring",
                "message": "Missing module docstring",
                "message-id": "C0114",
            },
        ]
        linter = PylintLinter()
        result = linter._parse(json.dumps(payload))

        assert result.ok
        assert len(result.findings) == 2

        first = result.findings[0]
        assert first.severity == Severity.ERROR
        assert first.rule == "undefined-variable"
        assert first.line == 5
        assert first.column == 4  # pylint 0-based -> 1-based
        assert first.end_line == 5

        second = result.findings[1]
        assert second.severity == Severity.SUGGESTION
        assert second.rule == "missing-module-docstring"

    def test_parse_invalid_json(self):
        linter = PylintLinter()
        result = linter._parse("not json at all")
        assert not result.ok
        assert result.errors

    def test_unknown_category_maps_to_warning(self):
        payload = [
            {
                "type": "unknown-kind",
                "path": "a.py",
                "symbol": "r",
                "message": "m",
                "line": 1,
                "column": 0,
            }
        ]
        linter = PylintLinter()
        result = linter._parse(json.dumps(payload))
        assert result.findings[0].severity == Severity.WARNING


class TestESLintParsing:
    def test_parse_json_findings(self):
        payload = [
            {
                "filePath": "src/index.js",
                "messages": [
                    {
                        "ruleId": "no-unused-vars",
                        "severity": 2,
                        "message": "'x' is defined but never used.",
                        "line": 3,
                        "column": 7,
                        "endLine": 3,
                        "endColumn": 8,
                    },
                    {
                        "ruleId": "no-debugger",
                        "severity": 1,
                        "message": "Unexpected 'debugger' statement.",
                        "line": 9,
                        "column": 1,
                    },
                    {
                        # fatal parse error: no ruleId
                        "fatal": True,
                        "severity": 2,
                        "message": "Parsing error: Unexpected token",
                        "line": 1,
                        "column": 1,
                    },
                ],
            }
        ]
        linter = ESLintLinter()
        result = linter._parse(json.dumps(payload))

        assert len(result.findings) == 2
        assert result.findings[0].severity == Severity.ERROR
        assert result.findings[0].rule == "no-unused-vars"
        assert result.findings[0].file == "src/index.js"
        assert result.findings[1].severity == Severity.WARNING

    def test_parse_invalid_json(self):
        linter = ESLintLinter()
        result = linter._parse("oops")
        assert not result.ok
        assert result.errors


class TestCheckstyleParsing:
    XML = """<?xml version="1.0"?>
<checkstyle version="13.9.0">
  <file name="src/Main.java">
    <error line="7" column="5" severity="error"
           message="Name 'x' must match pattern" 
           source="com.puppycrawl.tools.checkstyle.checks.naming.MemberNameCheck"/>
    <error line="12" column="1" severity="warning"
           message="Missing a Javadoc comment"
           source="com.puppycrawl.tools.checkstyle.checks.javadoc.JavadocTypeCheck"/>
  </file>
  <file name="src/Util.java">
    <error line="1" column="1" severity="info"
           message="Trailing spaces"
           source="com.puppycrawl.tools.checkstyle.checks.regexp.RegexpSinglelineCheck"/>
  </file>
</checkstyle>"""

    def test_parse_xml_findings(self):
        linter = CheckstyleLinter()
        result = linter._parse(self.XML)

        assert len(result.findings) == 3

        first = result.findings[0]
        assert first.severity == Severity.ERROR
        assert first.rule == "MemberNameCheck"
        assert first.file == "src/Main.java"
        assert first.line == 7
        assert first.column == 5

        third = result.findings[2]
        assert third.severity == Severity.SUGGESTION
        assert third.rule == "RegexpSinglelineCheck"

    def test_parse_invalid_xml(self):
        linter = CheckstyleLinter()
        result = linter._parse("<not-xml")
        assert not result.ok
        assert result.errors


class TestBanditParsing:
    def test_parse_json_findings(self):
        payload = {
            "errors": [],
            "results": [
                {
                    "code": "import subprocess\n",
                    "col_offset": 0,
                    "end_col_offset": 17,
                    "filename": "demo.py",
                    "issue_confidence": "HIGH",
                    "issue_cwe": {"id": 78},
                    "issue_severity": "LOW",
                    "issue_text": "Consider possible security implications.",
                    "line_number": 1,
                    "test_id": "B404",
                    "test_name": "blacklist",
                },
                {
                    "code": "return subprocess.Popen(cmd, shell=True)\n",
                    "col_offset": 11,
                    "end_col_offset": 44,
                    "filename": "demo.py",
                    "issue_confidence": "HIGH",
                    "issue_cwe": {"id": 78},
                    "issue_severity": "HIGH",
                    "issue_text": "shell=True is dangerous.",
                    "line_number": 4,
                    "test_id": "B602",
                    "test_name": "subprocess_popen_with_shell_equals_true",
                },
            ],
        }
        linter = BanditLinter()
        result = linter._parse(json.dumps(payload))

        assert len(result.findings) == 2
        assert result.ok

        first = result.findings[0]
        assert first.severity == Severity.SUGGESTION
        assert first.rule == "B404"
        assert first.file == "demo.py"
        assert first.line == 1
        assert first.column == 1

        second = result.findings[1]
        assert second.severity == Severity.ERROR
        assert second.rule == "B602"
        assert second.line == 4

    def test_parse_reports_bandit_errors(self):
        payload = {
            "errors": [
                {"filename": "bad.py", "reason": "Unable to parse"}
            ],
            "results": [],
        }
        linter = BanditLinter()
        result = linter._parse(json.dumps(payload))
        assert not result.ok
        assert any("bad.py" in e for e in result.errors)

    def test_parse_empty_clean_run(self):
        linter = BanditLinter()
        result = linter._parse(json.dumps({"errors": [], "results": []}))
        assert result.ok
        assert result.findings == []

    def test_parse_invalid_json_with_error_exit(self):
        linter = BanditLinter()
        result = linter._parse("not json", returncode=2)
        assert not result.ok
        assert result.errors


class TestSpotBugsParsing:
    XML = """<?xml version="1.0" encoding="UTF-8"?>
<BugCollection version="4.10.3" sequence="0">
  <Project projectName="">
    <Jar>/tmp/classes</Jar>
  </Project>
  <BugInstance type="NP_ALWAYS_NULL" priority="1" rank="5"
       abbrev="NP" category="CORRECTNESS">
    <ShortMessage>Null pointer dereference</ShortMessage>
    <LongMessage>Null pointer dereference of ? in Demo.main(String[])</LongMessage>
    <Class classname="Demo" primary="true">
      <SourceLine classname="Demo" start="1" end="10"
          sourcefile="Demo.java" sourcepath="Demo.java"/>
    </Class>
    <SourceLine classname="Demo" primary="true" start="9" end="9"
        sourcefile="Demo.java" sourcepath="Demo.java"
        role="SOURCE_LINE_DEREF"/>
  </BugInstance>
  <BugInstance type="DM_NUMBER_CTOR" priority="2" rank="11"
       abbrev="Dm" category="BAD_PRACTICE">
    <ShortMessage>Method invokes inefficient Number constructor</ShortMessage>
    <LongMessage>Demo.new Double(double)</LongMessage>
    <SourceLine classname="Demo" start="12" end="12"
        sourcefile="Demo.java" sourcepath="Demo.java"/>
  </BugInstance>
  <BugInstance type="DLS_DEAD_LOCAL_STORE" priority="3" rank="17"
       abbrev="DLS" category="STYLE">
    <ShortMessage>Dead store to local variable</ShortMessage>
    <LongMessage>Dead store to local variable x</LongMessage>
    <SourceLine classname="Demo" start="15" end="15"
        sourcefile="Demo.java" sourcepath="Demo.java"/>
  </BugInstance>
</BugCollection>"""

    def test_parse_xml_findings(self):
        linter = SpotBugsLinter()
        result = linter._parse(self.XML)

        assert len(result.findings) == 3
        assert result.ok

        first = result.findings[0]
        assert first.severity == Severity.ERROR  # priority 1
        assert first.rule == "NP_ALWAYS_NULL"
        assert first.line == 9  # primary SourceLine
        assert first.file == "Demo.java"

        second = result.findings[1]
        assert second.severity == Severity.WARNING  # priority 2

        third = result.findings[2]
        assert third.severity == Severity.SUGGESTION  # priority 3

    def test_remap_files_by_basename(self):
        from app.analysis.finding import Finding

        linter = SpotBugsLinter()
        result = linter._parse(self.XML)
        linter._remap_files(result, ["src/Demo.java"])
        assert all(f.file == "src/Demo.java" for f in result.findings)

    def test_remap_files_ambiguous_basename_unchanged(self):
        linter = SpotBugsLinter()
        result = linter._parse(self.XML)
        linter._remap_files(result, ["a/Demo.java", "b/Demo.java"])
        assert all(f.file == "Demo.java" for f in result.findings)
