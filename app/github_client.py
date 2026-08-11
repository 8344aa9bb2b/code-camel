from __future__ import annotations

from typing import Dict, List, Optional

import requests

from . import config

API_BASE = "https://api.github.com"
RAW_HEADERS = {"Accept": "application/vnd.github.raw+json"}


class GitHubClientError(Exception):
    """Raised when a GitHub API call fails."""


class GitHubClient:
    """Thin wrapper over the GitHub REST API for PR review."""

    def __init__(
        self,
        token: Optional[str] = None,
        installation_id: Optional[int | str] = None,
    ):
        if token:
            self._token = token
        elif installation_id is not None:
            from .github_app import installation_token

            self._token = installation_token(installation_id)
        elif config.GITHUB_TOKEN:
            self._token = config.GITHUB_TOKEN
        else:
            raise GitHubClientError(
                "No GitHub credentials; set GITHUB_TOKEN or pass installation_id."
            )
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
            }
        )

    def _get(self, url: str, **kwargs):
        resp = self._session.get(url, **kwargs)
        if not resp.ok:
            raise GitHubClientError(
                f"GET {url} -> {resp.status_code}: {resp.text[:300]}"
            )
        return resp

    def _post(self, url: str, payload: Dict):
        resp = self._session.post(url, json=payload)
        if not resp.ok:
            raise GitHubClientError(
                f"POST {url} -> {resp.status_code}: {resp.text[:300]}"
            )
        return resp

    def list_pr_files(self, owner: str, repo: str, pr_number: int) -> List[Dict]:
        """Return the list of files changed by a pull request."""
        url = f"{API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/files"
        files: List[Dict] = []
        page = 1
        while True:
            resp = self._get(url, params={"per_page": 100, "page": page})
            batch = resp.json()
            files.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return files

    def fetch_file_content(self, owner: str, repo: str, path: str, ref: str) -> bytes:
        """Return the raw content of *path* at commit *ref*."""
        url = f"{API_BASE}/repos/{owner}/{repo}/contents/{path}"
        resp = self._get(
            url, params={"ref": ref}, headers=RAW_HEADERS, timeout=60
        )
        return resp.content

    def post_comment(self, owner: str, repo: str, issue_number: int, body: str) -> Dict:
        """Post a comment on an issue or pull request."""
        url = f"{API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/comments"
        resp = self._post(url, {"body": body})
        return resp.json()
