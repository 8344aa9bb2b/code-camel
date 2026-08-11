import json

import pytest

from app.ai import LLMClient, LLMClientError, RefactorSuggestion, build_prompt, parse_response
from app.ai.code_smell import _extract_json, _severity
from app.analysis.finding import Finding, Severity
from app.analysis.pipeline import AnalysisReport
from app.reviewer import build_summary


def _report():
    return AnalysisReport(
        files_analyzed=["src/app.py"],
        findings=[
            Finding(
                linter="bandit",
                rule="B602",
                message="shell injection",
                severity=Severity.ERROR,
                file="src/app.py",
                line=7,
            )
        ],
    )


def test_parse_response_ok():
    text = json.dumps(
        {
            "suggestions": [
                {
                    "file": "src/app.py",
                    "line": 7,
                    "message": "Prefer subprocess with a list argument",
                    "severity": "warning",
                    "suggestion": "Use subprocess.run(['ls', '-l'])",
                    "reason": "Avoids shell injection",
                }
            ]
        }
    )
    suggestions = parse_response(text)
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.file == "src/app.py"
    assert s.line == 7
    assert s.severity == Severity.WARNING
    assert "subprocess" in s.suggestion


def test_parse_response_fenced():
    text = '```json\n{"suggestions": [{"file": "a.py", "message": "x", "severity": "error"}]}\n```'
    suggestions = parse_response(text)
    assert suggestions[0].message == "x"


def test_parse_response_invalid_json():
    with pytest.raises(LLMClientError):
        parse_response("not json")


def test_parse_response_skips_malformed_items():
    text = json.dumps(
        {
            "suggestions": [
                {"file": "a.py", "message": "ok", "severity": "error"},
                {"file": "b.py"},  # no message
                "junk",
            ]
        }
    )
    suggestions = parse_response(text)
    assert len(suggestions) == 1


def test_severity_fallback():
    assert _severity("Warning") == Severity.WARNING
    assert _severity("nonsense") == Severity.SUGGESTION


def test_extract_json_tolerates_fences():
    data = _extract_json("```json\n{\"a\": 1}\n```")
    assert data == {"a": 1}


def test_build_prompt_contains_findings_and_snippets():
    report = _report()
    messages = build_prompt(report, {"src/app.py": "import os\nos.system(x)"})
    user = messages[-1]["content"]
    assert "B602" in user
    assert "shell injection" in user
    assert "src/app.py" in user
    assert "os.system" in user


def test_build_prompt_empty():
    messages = build_prompt(AnalysisReport(), {})
    assert "No linter findings" in messages[-1]["content"]


def test_build_summary_with_suggestions():
    report = _report()
    suggestions = [
        RefactorSuggestion(
            file="src/app.py",
            line=7,
            message="Prefer subprocess list args",
            severity=Severity.WARNING,
            suggestion="subprocess.run(['ls'])",
            reason="Avoid shell injection",
        )
    ]
    body = build_summary(report, suggestions)
    assert "## AI Refactor Suggestions" in body
    assert "Prefer subprocess list args" in body
    assert "Suggested fix" in body
    assert "Avoid shell injection" in body


def test_llm_client_missing_key(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "LLM_API_KEY", None)
    with pytest.raises(LLMClientError):
        LLMClient()


def test_llm_client_complete(monkeypatch):
    class FakeResp:
        ok = True
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": '{"suggestions": []}'}}]}

    import requests

    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResp())
    client = LLMClient(api_key="test-key")
    content = client.complete([{"role": "user", "content": "hi"}])
    assert content == '{"suggestions": []}'


def test_llm_client_http_error(monkeypatch):
    class FakeResp:
        ok = False
        status_code = 500
        text = "boom"

    import requests

    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResp())
    client = LLMClient(api_key="test-key")
    with pytest.raises(LLMClientError):
        client.complete([{"role": "user", "content": "hi"}])
