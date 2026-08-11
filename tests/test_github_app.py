import base64
import json

import pytest
from joserfc import jwk

from app import config
from app.github_app import _create_app_jwt
from app.github_client import GitHubClient, GitHubClientError


@pytest.fixture
def rsa_key():
    return jwk.RSAKey.generate_key(2048)


def _claims(token: str) -> dict:
    seg = token.split(".")[1]
    seg += "=" * (-len(seg) % 4)
    return json.loads(base64.urlsafe_b64decode(seg))


def test_create_app_jwt(rsa_key, monkeypatch):
    monkeypatch.setattr(config, "GITHUB_APP_ID", "123456")
    monkeypatch.setattr(config, "GITHUB_PRIVATE_KEY", rsa_key.as_pem(private=True).decode())
    monkeypatch.setattr(config, "GITHUB_PRIVATE_KEY_PATH", None)

    token = _create_app_jwt()
    claims = _claims(token)

    assert claims["iss"] == "123456"
    assert claims["exp"] - claims["iat"] == 540
    assert len(token.split(".")) == 3


def test_create_app_jwt_missing_app_id(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_APP_ID", None)
    with pytest.raises(GitHubClientError):
        _create_app_jwt()


def test_create_app_jwt_missing_key(rsa_key, monkeypatch):
    monkeypatch.setattr(config, "GITHUB_APP_ID", "123456")
    monkeypatch.setattr(config, "GITHUB_PRIVATE_KEY", None)
    monkeypatch.setattr(config, "GITHUB_PRIVATE_KEY_PATH", None)
    with pytest.raises(GitHubClientError):
        _create_app_jwt()


def test_create_app_jwt_key_from_path(rsa_key, monkeypatch, tmp_path):
    key_path = tmp_path / "app.pem"
    key_path.write_text(rsa_key.as_pem(private=True).decode())

    monkeypatch.setattr(config, "GITHUB_APP_ID", "123456")
    monkeypatch.setattr(config, "GITHUB_PRIVATE_KEY", None)
    monkeypatch.setattr(config, "GITHUB_PRIVATE_KEY_PATH", str(key_path))

    token = _create_app_jwt()
    assert _claims(token)["iss"] == "123456"


def test_github_client_no_credentials(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_TOKEN", None)
    with pytest.raises(GitHubClientError):
        GitHubClient()
