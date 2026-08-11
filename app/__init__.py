from flask import Flask
from authlib.integrations.flask_client import OAuth
from . import config

oauth = OAuth()

def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY   # replace with secure key

    oauth.init_app(app)

    github = oauth.register(
        name="github",
        client_id=config.GITHUB_CLIENT_ID,
        client_secret=config.GITHUB_CLIENT_SECRET,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "repo user"},
    )

    from .routes import bp
    app.register_blueprint(bp)

    from .webhook import webhook_bp
    app.register_blueprint(webhook_bp)

    return app
