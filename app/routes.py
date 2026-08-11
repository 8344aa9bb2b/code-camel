from flask import Blueprint, redirect, url_for, session, render_template, request
from app import oauth
from . import config
from .dashboard import linked_repos, unlinked_repos, commit_heatmap, heatmap_weeks
from .github_client import GitHubClientError

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    user = session.get("user")
    if not user:
        return redirect(url_for("main.login"))
    return render_template(
        "dashboard.html",
        user=user,
        app_slug=config.GITHUB_APP_SLUG,
        **dashboard_data(),
    )


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("main.index"))
    if request.method == "POST":
        return _start_oauth()
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


@bp.route("/oauth/callback")
def callback():
    github = oauth.create_client("github")
    token = github.authorize_access_token()
    user = github.get("user").json()
    session["user"] = user
    session["token"] = token
    return redirect(url_for("main.index"))


def _start_oauth():
    github = oauth.create_client("github")
    redirect_uri = url_for("main.callback", _external=True)
    return github.authorize_redirect(redirect_uri)


def dashboard_data() -> dict:
    token = (session.get("token") or {}).get("access_token")
    if not token:
        return {"linked": [], "unlinked": [], "error": "No access token in session."}

    linked: list = []
    unlinked: list = []
    error = None
    try:
        linked = linked_repos(token)
        unlinked = unlinked_repos(token)
    except GitHubClientError as exc:
        error = str(exc)

    heatmaps = {}
    for repo in linked:
        try:
            activity = commit_heatmap(repo["owner"], repo["name"], repo["installation_id"])
            if activity:
                heatmaps[repo["full_name"]] = heatmap_weeks(activity)
        except GitHubClientError:
            continue

    return {"linked": linked, "unlinked": unlinked, "heatmaps": heatmaps, "error": error}
