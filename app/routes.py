from flask import Blueprint, redirect, url_for, session
from app import oauth

bp = Blueprint("main", __name__)

@bp.route("/")
def index():
    user = session.get("user")
    if user:
        return f"Hello, {user['login']}!"
    return "Welcome! <a href='/login'>Login with GitHub</a>"

@bp.route("/login")
def login():
    github = oauth.create_client("github")
    redirect_uri = url_for("main.callback", _external=True)
    return github.authorize_redirect(redirect_uri)

@bp.route("/oauth/callback")
def callback():
    github = oauth.create_client("github")
    token = github.authorize_access_token()
    user = github.get("user").json()
    session["user"] = user
    session["token"] = token
    return redirect(url_for("main.index"))
