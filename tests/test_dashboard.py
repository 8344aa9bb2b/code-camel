import pytest
from joserfc import jwk

from app import create_app, config
from app.dashboard import _level, heatmap_weeks
from app.github_client import GitHubClientError


def test_level_thresholds():
    assert _level(0) == 0
    assert _level(1) == 1
    assert _level(4) == 1
    assert _level(5) == 2
    assert _level(9) == 2
    assert _level(10) == 3
    assert _level(19) == 3
    assert _level(20) == 4
    assert _level(500) == 4


def test_heatmap_weeks_shape():
    activity = [{"week": 1_700_000_000, "total": 5, "days": [0, 1, 2, 3, 4, 5, 6]}]
    weeks = heatmap_weeks(activity)
    assert len(weeks) == 1
    assert len(weeks[0]["days"]) == 7
    assert weeks[0]["days"][0]["count"] == 0
    assert weeks[0]["days"][6]["count"] == 6
    assert weeks[0]["days"][6]["date"]
    assert weeks[0]["total"] == 5


def test_login_requires_no_auth(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Sign in with GitHub" in resp.data


def test_root_redirects_to_login(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_root_renders_dashboard(monkeypatch, client):
    import app.routes as routes

    def fake_linked(token):
        return [
            {
                "full_name": "acme/web",
                "name": "web",
                "owner": "acme",
                "private": True,
                "html_url": "https://github.com/acme/web",
                "installation_id": 1,
            }
        ]

    def fake_unlinked(token):
        return [
            {
                "full_name": "acme/api",
                "name": "api",
                "owner": "acme",
                "private": False,
                "html_url": "https://github.com/acme/api",
            }
        ]

    def fake_heatmap(owner, repo, installation_id):
        return [
            {"week": 1_700_000_000, "total": 5, "days": [0, 1, 2, 3, 4, 5, 6]}
        ]

    monkeypatch.setattr(routes, "linked_repos", fake_linked)
    monkeypatch.setattr(routes, "unlinked_repos", fake_unlinked)
    monkeypatch.setattr(routes, "commit_heatmap", fake_heatmap)

    with client.session_transaction() as sess:
        sess["user"] = {"login": "dev", "avatar_url": ""}
        sess["token"] = {"access_token": "fake"}

    resp = client.get("/")
    assert resp.status_code == 200
    assert b"acme/web" in resp.data
    assert b"acme/api" in resp.data
    assert b"Available to link" in resp.data
    assert b"heat-cell" in resp.data
    assert b"Dashboard" in resp.data


def test_dashboard_error_shown(monkeypatch, client):
    import app.routes as routes

    def boom(token):
        raise GitHubClientError("nope")

    monkeypatch.setattr(routes, "linked_repos", boom)
    monkeypatch.setattr(routes, "unlinked_repos", lambda token: [])

    with client.session_transaction() as sess:
        sess["user"] = {"login": "dev", "avatar_url": ""}
        sess["token"] = {"access_token": "fake"}

    resp = client.get("/")
    assert resp.status_code == 200
    assert b"nope" in resp.data


def test_logout_clears_session(client):
    with client.session_transaction() as sess:
        sess["user"] = {"login": "dev"}
        sess["token"] = {"access_token": "fake"}
    resp = client.get("/logout")
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert "user" not in sess
