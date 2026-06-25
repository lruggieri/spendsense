"""Web endpoints for managing MCP API keys."""
import logging

from flask import Blueprint, g, jsonify, render_template, request

from presentation.web.decorators import login_required
from presentation.web.utils import get_encryption_service

logger = logging.getLogger(__name__)

api_keys_bp = Blueprint("api_keys", __name__)


@api_keys_bp.route("/settings/api-keys")
@login_required
def api_keys_page():
    return render_template("api_keys.html")


@api_keys_bp.route("/api/mcp-keys", methods=["GET"])
@login_required
def list_keys():
    user_id = request.user_id  # type: ignore[attr-defined]
    svc = get_encryption_service()
    keys = svc.list_mcp_api_keys(user_id)
    safe = [
        {k: v for k, v in row.items() if k not in ("token_hash",)}
        for row in keys
    ]
    return jsonify({"keys": safe})


@api_keys_bp.route("/api/mcp-keys/create", methods=["POST"])
@login_required
def create_key():
    user_id = request.user_id  # type: ignore[attr-defined]
    data = request.get_json(force=True) or {}
    scope = data.get("scope", "read")
    label = data.get("label", "")
    expires_at = data.get("expires_at", None)

    if scope not in ("read", "readwrite"):
        return jsonify({"error": "scope must be 'read' or 'readwrite'"}), 400
    if not label:
        return jsonify({"error": "label is required"}), 400

    dek_b64 = getattr(g, "encryption_key", None)
    svc = get_encryption_service()
    try:
        raw = svc.create_mcp_api_key(user_id, scope, label, expires_at, dek_b64)
    except Exception as exc:
        logger.error("Failed to create MCP API key for user %s: %s", user_id, type(exc).__name__)
        return jsonify({"error": "could not create key"}), 500

    logger.info("Created MCP key for user %s scope=%s", user_id, scope)
    return jsonify({"key": raw, "message": "Store this key — it will not be shown again."})


@api_keys_bp.route("/api/mcp-keys/revoke", methods=["POST"])
@login_required
def revoke_key():
    user_id = request.user_id  # type: ignore[attr-defined]
    data = request.get_json(force=True) or {}
    key_id = data.get("key_id")
    if not key_id:
        return jsonify({"error": "key_id required"}), 400

    svc = get_encryption_service()
    revoked = svc.revoke_mcp_api_key(user_id, key_id)
    if not revoked:
        return jsonify({"error": "key not found or already revoked"}), 404

    logger.info("Revoked MCP key %s for user %s", key_id[:8], user_id)
    return jsonify({"revoked": True})
