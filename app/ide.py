from __future__ import annotations

import base64
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from . import config, store
from .analysis.pipeline import _SUPPORTED_EXTENSIONS, AnalysisReport, analyze_files
from .analysis.registry import app_registry
from .ai import LLMClientError, generate_refactor_suggestions
from .github_app import _create_app_jwt, installation_token
from .github_client import GitHubClient, GitHubClientError
from .reviewer import _changed_files, _supported_files, analyze_pr_changes

API_BASE = "https://api.github.com"
MAX_VIEWABLE = 5 * 1024 * 1024  # 5 MB
LINT_CACHE_TTL = 300  # seconds

ide_bp = Blueprint("ide", __name__)

_junk_anywhere = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
}
_junk_root = {"dist", "build", "target"}

_token_cache: Dict[str, tuple] = {}
_info_cache: Dict[str, tuple] = {}
_lint_cache: Dict[str, tuple] = {}


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


def _cached_installation_token(installation_id: int | str) -> str:
    key = str(installation_id)
    hit = _token_cache.get(key)
    if hit and hit[0] > time.time() + 60:
        return hit[1]
    token = installation_token(installation_id)
    _token_cache[key] = (time.time() + 3600, token)
    return token


def _get_json(url: str, token: str, params: Optional[Dict] = None) -> Dict:
    resp = requests.get(url, params=params, headers=_headers(token), timeout=30)
    if not resp.ok:
        raise GitHubClientError(f"GET {url} -> {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def _repo_info(owner: str, repo: str) -> Dict:
    key = f"{owner}/{repo}"
    hit = _info_cache.get(key)
    if hit and hit[0] > time.time() + 300:
        return hit[1]
    headers = {"Authorization": f"Bearer {_create_app_jwt()}"}
    resp = requests.get(
        f"{API_BASE}/repos/{owner}/{repo}/installation",
        headers=headers,
        timeout=30,
    )
    if not resp.ok:
        raise GitHubClientError(
            f"GET /repo/{key}/installation -> {resp.status_code}: {resp.text[:300]}"
        )
    installation_id = resp.json()["id"]
    token = _cached_installation_token(installation_id)
    repo_data = _get_json(f"{API_BASE}/repos/{owner}/{repo}", token)
    info = {"installation_id": installation_id, "default_branch": repo_data["default_branch"]}
    _info_cache[key] = (time.time() + 300, info)
    return info


def _git_client(owner: str, repo: str) -> GitHubClient:
    installation_id, _ = _repo_info(owner, repo)
    token = _cached_installation_token(installation_id)
    return GitHubClient(token=token)


def _tree(owner: str, repo: str, branch: str) -> List[Dict]:
    token = _git_client(owner, repo)._token
    data = _get_json(
        f"{API_BASE}/repos/{owner}/{repo}/git/trees/{branch}",
        token,
        params={"recursive": 1},
    )
    entries: List[Dict] = []
    for item in data.get("tree", []):
        if item.get("type") != "blob":
            continue
        path = item["path"]
        parts = path.split("/")
        if any(p in _junk_anywhere for p in parts):
            continue
        if parts[0] in _junk_root:
            continue
        suffix = Path(path).suffix.lower()
        entries.append(
            {
                "path": path,
                "sha": item["sha"],
                "size": item.get("size", 0),
                "lintable": suffix in _SUPPORTED_EXTENSIONS,
            }
        )
    return entries


def _fetch_content(
    owner: str, repo: str, path: str, ref: str, blob_sha: str, size: int
) -> bytes:
    """Return raw file bytes, using raw contents API for small files and
    the git blobs API for anything larger (GitHub caps raw at 1 MiB)."""
    token = _git_client(owner, repo)._token
    if size <= 1024 * 1024:
        url = f"{API_BASE}/repos/{owner}/{repo}/contents/{path}"
        resp = requests.get(
            url,
            params={"ref": ref},
            headers={**_headers(token), "Accept": "application/vnd.github.raw+json"},
            timeout=60,
        )
        if resp.ok:
            return resp.content
    if not blob_sha:
        raise GitHubClientError("No blob sha available for content fetch.")
    blob = _get_json(f"{API_BASE}/repos/{owner}/{repo}/git/blobs/{blob_sha}", token)
    if blob.get("encoding") == "base64":
        return base64.b64decode(blob.get("content", ""))
    return blob.get("content", "").encode("utf-8")


def _lint_file(owner: str, repo: str, path: str, sha: str) -> AnalysisReport:
    key = f"{owner}/{repo}/{sha}/{path}"
    hit = _lint_cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    tree = _tree(owner, repo, sha)
    entry = next((e for e in tree if e["path"] == path), None)
    if entry is None:
        raise GitHubClientError(f"path not found in tree: {path}")

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        target = dest / path
        target.parent.mkdir(parents=True, exist_ok=True)
        content = _fetch_content(owner, repo, path, sha, entry["sha"], entry["size"])
        target.write_bytes(content)
        report = analyze_files([str(target)], registry=app_registry(), cwd=str(dest))

    _lint_cache[key] = (time.time() + LINT_CACHE_TTL, report)
    return report


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------


@ide_bp.route("/ide/<owner>/<repo>")
def ide_page(owner: str, repo: str):
    if not session.get("user"):
        return redirect(url_for("main.login"))
    return render_template(
        "ide.html",
        owner=owner,
        repo=repo,
        mode="branch",
        pr_number=None,
        user=session.get("user"),
    )


@ide_bp.route("/ide/<owner>/<repo>/pr/<int:pr_number>")
def ide_page_pr(owner: str, repo: str, pr_number: int):
    if not session.get("user"):
        return redirect(url_for("main.login"))
    return render_template(
        "ide.html",
        owner=owner,
        repo=repo,
        mode="pr",
        pr_number=pr_number,
        user=session.get("user"),
    )


# --------------------------------------------------------------------------
# JSON API
# --------------------------------------------------------------------------


def _authed():
    if not session.get("user"):
        return jsonify({"error": "Not authenticated"}), 401
    return None


@ide_bp.route("/api/ide/info")
def api_info():
    blocked = _authed()
    if blocked:
        return blocked
    owner, repo = request.args["owner"], request.args["repo"]
    try:
        return jsonify(_repo_info(owner, repo))
    except GitHubClientError as exc:
        return jsonify({"error": str(exc)}), 502


@ide_bp.route("/api/ide/tree")
def api_tree():
    blocked = _authed()
    if blocked:
        return blocked
    owner, repo = request.args["owner"], request.args["repo"]
    branch = request.args.get("branch")
    try:
        info = _repo_info(owner, repo)
        branch = branch or info["default_branch"]
        return jsonify({"branch": branch, "files": _tree(owner, repo, branch)})
    except GitHubClientError as exc:
        return jsonify({"error": str(exc)}), 502


@ide_bp.route("/api/ide/lint")
def api_lint():
    blocked = _authed()
    if blocked:
        return blocked
    owner, repo = request.args["owner"], request.args["repo"]
    path = request.args.get("path", "")
    sha = request.args.get("sha", "")
    if Path(path).suffix.lower() not in _SUPPORTED_EXTENSIONS:
        return jsonify({"findings": [], "errors": []})
    try:
        report = _lint_file(owner, repo, path, sha)
        return jsonify(
            {
                "findings": [f.to_dict() for f in report.findings],
                "errors": report.errors,
            }
        )
    except GitHubClientError as exc:
        return jsonify({"error": str(exc)}), 502


@ide_bp.route("/api/ide/content")
def api_content():
    blocked = _authed()
    if blocked:
        return blocked
    owner, repo = request.args["owner"], request.args["repo"]
    path = request.args.get("path", "")
    ref = request.args.get("ref", "")
    blob_sha = request.args.get("blob", "")
    size = int(request.args.get("size", "0"))
    try:
        raw = _fetch_content(owner, repo, path, ref, blob_sha, size)
    except GitHubClientError as exc:
        return jsonify({"error": str(exc)}), 502
    if len(raw) > MAX_VIEWABLE:
        return jsonify({"error": "File too large to display."}), 413
    try:
        return jsonify({"content": raw.decode("utf-8")})
    except UnicodeDecodeError:
        return jsonify({"content": raw.decode("utf-8", errors="replace")})


@ide_bp.route("/api/ide/refactor", methods=["POST"])
def api_refactor():
    blocked = _authed()
    if blocked:
        return blocked
    data = request.get_json(silent=True) or {}
    owner, repo = data["owner"], data["repo"]
    path = data.get("path", "")
    sha = data.get("sha", "")
    if Path(path).suffix.lower() not in _SUPPORTED_EXTENSIONS:
        return jsonify({"suggestions": []})
    try:
        report = _lint_file(owner, repo, path, sha)
        entry = next((e for e in _tree(owner, repo, sha) if e["path"] == path), None)
        content = (
            _fetch_content(owner, repo, path, sha, entry["sha"], entry["size"])
            if entry
            else b""
        )
        snippets = _snippet_for(path, content)
        suggestions = generate_refactor_suggestions(report, snippets)
        return jsonify({"suggestions": [s.to_dict() for s in suggestions]})
    except (LLMClientError, GitHubClientError) as exc:
        return jsonify({"error": str(exc)}), 502


def _snippet_for(path: str, raw: bytes) -> Dict[str, str]:
    """Gather a source snippet for the file so the AI has context."""
    if not raw:
        return {}
    content = raw.decode("utf-8", errors="replace")
    lines = content.splitlines()
    if len(lines) > 200:
        content = "\n".join(lines[:200]) + "\n# ... (truncated)"
    return {path: content} if content.strip() else {}


@ide_bp.route("/api/ide/pr-findings")
def api_pr_findings():
    blocked = _authed()
    if blocked:
        return blocked
    owner, repo = request.args["owner"], request.args["repo"]
    pr_number = int(request.args.get("pr_number", 0))
    review = store.get_pr_review(f"{owner}/{repo}", pr_number)
    return jsonify({"files": review["files"], "count": review["count"]})


@ide_bp.route("/api/ide/pr-files")
def api_pr_files():
    blocked = _authed()
    if blocked:
        return blocked
    owner, repo = request.args["owner"], request.args["repo"]
    pr_number = int(request.args.get("pr_number", 0))
    try:
        client = _git_client(owner, repo)
        files = _changed_files(client.list_pr_files(owner, repo, pr_number))
        result = []
        for f in files:
            result.append(
                {
                    "path": f["filename"],
                    "status": f.get("status"),
                    "additions": f.get("additions"),
                    "deletions": f.get("deletions"),
                }
            )
        return jsonify({"files": result})
    except GitHubClientError as exc:
        return jsonify({"error": str(exc)}), 502


@ide_bp.route("/api/ide/prs")
def api_prs():
    blocked = _authed()
    if blocked:
        return blocked
    owner, repo = request.args["owner"], request.args["repo"]
    token = _git_client(owner, repo)._token
    try:
        data = requests.get(
            f"{API_BASE}/repos/{owner}/{repo}/pulls",
            params={"state": "open", "per_page": 50},
            headers=_headers(token),
            timeout=30,
        )
        if not data.ok:
            raise GitHubClientError(f"GET pulls -> {data.status_code}")
        return jsonify(
            {
                "prs": [
                    {
                        "number": p["number"],
                        "title": p["title"],
                        "head": p["head"]["sha"],
                    }
                    for p in data.json()
                ]
            }
        )
    except GitHubClientError as exc:
        return jsonify({"error": str(exc)}), 502


@ide_bp.route("/api/ide/pr-analyze", methods=["POST"])
def api_pr_analyze():
    blocked = _authed()
    if blocked:
        return blocked
    data = request.get_json(silent=True) or {}
    owner, repo = data["owner"], data["repo"]
    pr_number = int(data.get("pr_number", 0))
    head_sha = data.get("head_sha", "")
    try:
        client = _git_client(owner, repo)
        report, suggestions = analyze_pr_changes(
            owner, repo, pr_number, head_sha, client=client
        )
        store.save_pr_review(f"{owner}/{repo}", pr_number, head_sha, report, suggestions)
        return jsonify({"count": len(report.findings)})
    except GitHubClientError as exc:
        return jsonify({"error": str(exc)}), 502