from flask import Blueprint

bp = Blueprint("main", __name__)

@bp.route("/")
def index():
    return "Flask GitHub Agent Running! Render CI/CD"
