from __future__ import annotations

import base64
import time
from typing import Optional

import requests
from joserfc import jwt, jwk

from . import config
from .github_client import GitHubClientError

API_BASE = "https://api.github.com"


def _load_private_key() -> str:
    """Return the app private key as PEM text."""
    if config.GITHUB_PRIVATE_KEY_PATH:
        with open(config.GITHUB_PRIVATE_KEY_PATH, "r", encoding="utf-8") as fh:
            return fh.read()
    if config.GITHUB_PRIVATE_KEY:
        raw = config.GITHUB_PRIVATE_KEY.strip()
        if raw.startswith("-----BEGIN"):
            return raw
        # Accept base64-encoded PEM so it fits in a single env var.
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
        except Exception:
            return raw
        return decoded
    raise GitHubClientError(
        "GitHub App private key not set; provide GITHUB_PRIVATE_KEY or "
        "GITHUB_PRIVATE_KEY_PATH."
    )


def _create_app_jwt() -> str:
    """Create a short-lived JWT signed with the GitHub App private key."""
    if not config.GITHUB_APP_ID:
        raise GitHubClientError("GITHUB_APP_ID is not set.")
    now = int(time.time())
    header = {"alg": "RS256"}
    payload = {"iat": now, "exp": now + 9 * 60, "iss": config.GITHUB_APP_ID}
    key = jwk.import_key(_load_private_key(), key_type="RSA")
    token = jwt.encode(header, payload, key)
    return str(token)


def installation_token(installation_id: int | str, app_jwt: Optional[str] = None) -> str:
    """Exchange a GitHub App JWT for an installation access token."""
    url = f"{API_BASE}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt or _create_app_jwt()}",
        "Accept": "application/vnd.github+json",
    }
    resp = requests.post(url, headers=headers, timeout=30)
    if not resp.ok:
        raise GitHubClientError(
            f"POST {url} -> {resp.status_code}: {resp.text[:300]}"
        )
    return resp.json()["token"]
