from flask import Blueprint, request, jsonify
import hmac
import hashlib
import threading
from . import config
from .github_client import GitHubClientError
from .reviewer import review_pull_request

webhook_bp = Blueprint("webhook", __name__)

def verify_signature(payload, signature):
    mac = hmac.new(config.WEBHOOK_SECRET.encode(), msg=payload, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected_signature, signature)

@webhook_bp.route("/webhook", methods=["POST"])
def webhook():
    payload = request.data
    signature = request.headers.get("X-Hub-Signature-256")

    if not verify_signature(payload, signature):
        return "Invalid signature", 403

    event = request.headers.get("X-GitHub-Event")
    data = request.json

    if event == "pull_request":
        action = data["action"]
        pr = data["pull_request"]
        repo = data["repository"]["full_name"]
        owner, repo_name = repo.split("/", 1)

        print(f"PR {action} in {repo}: #{pr['number']} - {pr['title']}")

        if action in ("opened", "synchronize", "reopened"):
            threading.Thread(
                target=_run_review,
                args=(owner, repo_name, pr["number"], pr["head"]["sha"]),
                daemon=True,
            ).start()

    return jsonify({"status": "ok"})

def _run_review(owner, repo, pr_number, head_sha):
    try:
        review_pull_request(owner, repo, pr_number, head_sha)
    except GitHubClientError as exc:
        print(f"Review failed for {owner}/{repo}#{pr_number}: {exc}")
