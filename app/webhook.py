from flask import Blueprint, request, jsonify
import hmac
import hashlib
from . import config

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

        print(f"PR {action} in {repo}: #{pr['number']} - {pr['title']}")

        # Example: handle PR opened
        if action == "opened":
            # custom logic here
            pass

    return jsonify({"status": "ok"})
