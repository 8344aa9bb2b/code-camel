from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests

from .github_app import installation_token
from .github_client import GitHubClientError

API_BASE = "https://api.github.com"


def _auth_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


def _get_json(url: str, token: str, params: Optional[Dict] = None) -> Dict:
    resp = requests.get(url, params=params, headers=_auth_headers(token), timeout=30)
    if not resp.ok:
        raise GitHubClientError(f"GET {url} -> {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def user_repos(token: str) -> List[Dict]:
    """All repositories the authenticated user can access."""
    repos: List[Dict] = []
    page = 1
    while True:
        data = _get_json(
            f"{API_BASE}/user/repos",
            token,
            params={
                "per_page": 100,
                "page": page,
                "affiliation": "owner,collaborator,organization_member",
            },
        )
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    return repos


def linked_repos(token: str) -> List[Dict]:
    """Repositories the GitHub App is installed on, reachable by the user."""
    linked: List[Dict] = []
    page = 1
    while True:
        data = _get_json(
            f"{API_BASE}/user/installations",
            token,
            params={"per_page": 100, "page": page},
        )
        installations = data.get("installations", [])
        for inst in installations:
            try:
                inst_token = installation_token(inst["id"])
            except GitHubClientError:
                continue
            repos = _get_json(
                inst["repositories_url"], inst_token, params={"per_page": 100}
            )
            for r in repos.get("repositories", []):
                linked.append(
                    {
                        "full_name": r["full_name"],
                        "name": r["name"],
                        "owner": r["owner"]["login"],
                        "private": r["private"],
                        "html_url": r["html_url"],
                        "installation_id": inst["id"],
                    }
                )
        total = data.get("total_count", 0)
        if not installations or page * 100 >= total:
            break
        page += 1
    return linked


def unlinked_repos(token: str) -> List[Dict]:
    """Repositories the user can access but the app is not installed on."""
    linked = {r["full_name"] for r in linked_repos(token)}
    result: List[Dict] = []
    for r in user_repos(token):
        if r["full_name"] in linked:
            continue
        result.append(
            {
                "full_name": r["full_name"],
                "name": r["name"],
                "owner": r["owner"]["login"],
                "private": r["private"],
                "html_url": r["html_url"],
            }
        )
    return result


def commit_heatmap(owner: str, repo: str, installation_id: int | str) -> Optional[List[Dict]]:
    """Weekly commit counts for the last year; None if GitHub is still computing."""
    token = installation_token(installation_id)
    url = f"{API_BASE}/repos/{owner}/{repo}/stats/commit_activity"
    resp = requests.get(url, headers=_auth_headers(token), timeout=30)
    if resp.status_code in (202, 403, 404) or not resp.ok:
        return None
    data = resp.json()
    return data if isinstance(data, list) else None


def _level(count: int) -> int:
    if count <= 0:
        return 0
    if count < 5:
        return 1
    if count < 10:
        return 2
    if count < 20:
        return 3
    return 4


def heatmap_weeks(activity: List[Dict]) -> List[Dict]:
    """Convert the API payload into a GitHub-style 7xN grid of cells."""
    weeks: List[Dict] = []
    for w in activity:
        start = datetime.fromtimestamp(w["week"], tz=timezone.utc)
        days = []
        for i, count in enumerate(w["days"]):
            date = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            days.append({"level": _level(count), "count": count, "date": date})
        weeks.append({"days": days, "total": w.get("total", 0)})
    return weeks
