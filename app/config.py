import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_CLIENT_ID = os.getenv("CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("CLIENT_SECRET")
GITHUB_REDIRECT_URI = "http://localhost:5000/callback"  # update for production
SECRET_KEY = os.getenv("SECRET_KEY")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# GitHub API token for reading PR files and posting review comments.
# Only needed if you use a PAT instead of GitHub App installation tokens.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# GitHub App credentials for installation-token auth.
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_PRIVATE_KEY = os.getenv("GITHUB_PRIVATE_KEY")  # PEM, or base64-encoded PEM
GITHUB_PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH")  # alternative

# --- Analysis / linter configuration -------------------------------
LINTER_TIMEOUT = int(os.getenv("LINTER_TIMEOUT", "120"))
PYLINT_CMD = os.getenv("PYLINT_CMD") or None
BANDIT_CMD = os.getenv("BANDIT_CMD") or None
ESLINT_CMD = os.getenv("ESLINT_CMD") or None
CHECKSTYLE_JAR = os.getenv("CHECKSTYLE_JAR") or None
CHECKSTYLE_CONFIG = os.getenv("CHECKSTYLE_CONFIG") or None
SPOTBUGS_JAR = os.getenv("SPOTBUGS_JAR") or None
