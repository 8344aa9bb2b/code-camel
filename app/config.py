import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_CLIENT_ID = os.getenv("CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("CLIENT_SECRET")
GITHUB_REDIRECT_URI = "http://localhost:5000/callback"  # update for production
SECRET_KEY = os.getenv("SECRET_KEY")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# --- Analysis / linter configuration -------------------------------
LINTER_TIMEOUT = int(os.getenv("LINTER_TIMEOUT", "120"))
PYLINT_CMD = os.getenv("PYLINT_CMD") or None
BANDIT_CMD = os.getenv("BANDIT_CMD") or None
ESLINT_CMD = os.getenv("ESLINT_CMD") or None
CHECKSTYLE_JAR = os.getenv("CHECKSTYLE_JAR") or None
CHECKSTYLE_CONFIG = os.getenv("CHECKSTYLE_CONFIG") or None
SPOTBUGS_JAR = os.getenv("SPOTBUGS_JAR") or None
