import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_CLIENT_ID = os.getenv("CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("CLIENT_SECRET")
GITHUB_REDIRECT_URI = "http://localhost:5000/callback"  # update for production
SECRET_KEY = os.getenv("SECRET_KEY")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
