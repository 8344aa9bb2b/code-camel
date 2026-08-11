from flask import Blueprint, request, jsonify

webhook_bp = Blueprint("webhook", __name__)

@webhook_bp.route("/webhook", methods=["POST"])
def webhook():
    event = request.headers.get("X-GitHub-Event")
    payload = request.json
    print(f"Received event: {event}")
    return jsonify({"status": "ok"}), 200
