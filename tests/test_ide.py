import pytest

from app import store
from app.analysis.finding import Finding, Severity
from app.analysis.pipeline import AnalysisReport
from app.ide import _junk_anywhere, _junk_root, _tree, _snippet_for


def _fake_tree_response(monkeypatch, entries):
    import app.ide as ide

    monkeypatch.setattr(
        ide,
        "_get_json",
        lambda url, token, params=None: {"tree": entries},
    )
    monkeypatch.setattr(ide, "_git_client", lambda o, r: type("C", (), {"_token": "t"})())


def test_tree_filters_junk(monkeypatch):
    entries = [
        {"type": "blob", "path": "app/main.py", "sha": "s1", "size": 10},
        {"type": "blob", "path": "node_modules/x.js", "sha": "s2", "size": 10},
        {"type": "blob", "path": "dist/bundle.js", "sha": "s3", "size": 10},
        {"type": "blob", "path": ".git/config", "sha": "s4", "size": 10},
        {"type": "blob", "path": "docs/readme.md", "sha": "s5", "size": 10},
        {"type": "tree", "path": "app", "sha": "s6", "size": 0},
        {"type": "blob", "path": "src/deep/__pycache__/x.py", "sha": "s7", "size": 10},
        {"type": "blob", "path": "src/keep.py", "sha": "s8", "size": 10},
    ]
    _fake_tree_response(monkeypatch, entries)
    result = _tree("acme", "web", "main")
    paths = [r["path"] for r in result]
    assert "app/main.py" in paths
    assert "docs/readme.md" in paths
    assert "src/keep.py" in paths
    assert "node_modules/x.js" not in paths
    assert "dist/bundle.js" not in paths
    assert ".git/config" not in paths
    assert "src/deep/__pycache__/x.py" not in paths


def test_tree_marks_lintable(monkeypatch):
    entries = [
        {"type": "blob", "path": "a.py", "sha": "s1", "size": 1},
        {"type": "blob", "path": "b.txt", "sha": "s2", "size": 1},
    ]
    _fake_tree_response(monkeypatch, entries)
    result = _tree("acme", "web", "main")
    by_path = {r["path"]: r for r in result}
    assert by_path["a.py"]["lintable"] is True
    assert by_path["b.txt"]["lintable"] is False


def test_snippet_truncates_long_files():
    content = ("line\n" * 250).encode()
    snippets = _snippet_for("a.py", content)
    assert "truncated" in snippets["a.py"]
    assert len(snippets["a.py"].splitlines()) <= 201


def test_snippet_empty_for_no_content():
    assert _snippet_for("a.py", b"") == {}


def test_ide_page_requires_login(client):
    resp = client.get("/ide/acme/web")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_ide_page_renders_for_user(client):
    with client.session_transaction() as sess:
        sess["user"] = {"login": "dev", "avatar_url": ""}
    resp = client.get("/ide/acme/web")
    assert resp.status_code == 200
    assert b"ide.html" not in resp.data  # rendered, not a redirect
    assert b"Problems" in resp.data
    assert b"monaco" in resp.data


def test_ide_pr_page_renders_for_user(client):
    with client.session_transaction() as sess:
        sess["user"] = {"login": "dev", "avatar_url": ""}
    resp = client.get("/ide/acme/web/pr/7")
    assert resp.status_code == 200
    assert b"PR #7" in resp.data


def test_api_requires_auth(client):
    for url in (
        "/api/ide/info?owner=acme&repo=web",
        "/api/ide/tree?owner=acme&repo=web",
        "/api/ide/lint?owner=acme&repo=web&path=a.py&sha=main",
        "/api/ide/prs?owner=acme&repo=web",
        "/api/ide/pr-findings?owner=acme&repo=web&pr_number=1",
    ):
        resp = client.get(url)
        assert resp.status_code == 401, url


def test_api_info_authed(monkeypatch, client):
    import app.ide as ide

    monkeypatch.setattr(
        ide, "_repo_info", lambda o, r: {"installation_id": 1, "default_branch": "main"}
    )
    with client.session_transaction() as sess:
        sess["user"] = {"login": "dev", "avatar_url": ""}
    resp = client.get("/api/ide/info?owner=acme&repo=web")
    assert resp.status_code == 200
    assert resp.get_json()["default_branch"] == "main"


def test_api_pr_findings_authed(monkeypatch, client, tmp_path):
    import app.ide as ide

    store._reset_path(str(tmp_path / "ide.db"))
    report = AnalysisReport(
        findings=[
            Finding(
                linter="pylint", rule="E", message="m", severity=Severity.ERROR,
                file="a.py", line=3,
            )
        ]
    )
    store.save_pr_review("acme/web", 2, "s", report, [])

    with client.session_transaction() as sess:
        sess["user"] = {"login": "dev", "avatar_url": ""}
    resp = client.get("/api/ide/pr-findings?owner=acme&repo=web&pr_number=2")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 1
    assert "a.py" in data["files"]


def test_pr_findings_empty_when_none(client):
    with client.session_transaction() as sess:
        sess["user"] = {"login": "dev", "avatar_url": ""}
    resp = client.get("/api/ide/pr-findings?owner=acme&repo=web&pr_number=99")
    assert resp.status_code == 200
    assert resp.get_json()["count"] == 0
