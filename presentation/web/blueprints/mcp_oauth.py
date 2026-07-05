"""Flask consent + passkey-unlock page for the MCP OAuth 2.1 authorize flow.

`SpendSenseOAuthProvider.authorize()` (presentation/mcp_server/oauth_provider.py)
starts a pending authorization transaction and redirects the user's browser
here (`/mcp-consent?txn=...`). This blueprint:

1. Requires login (reuses the existing session-cookie auth).
2. If the account is encrypted and the DEK isn't already unlocked in this
   browser session (`g.encryption_key` absent), shows the existing
   passkey-unlock UI first - the DEK only exists client-side, and must be
   carried across the OAuth back-channel gap via the authorization code
   (see `OAuthService.issue_code`'s docstring).
3. Otherwise shows a consent screen naming the client + requested scopes.
4. On Approve, mints a code and redirects to the client's `redirect_uri`;
   on Deny, redirects with `error=access_denied`.
"""
import json
import logging

from flask import Blueprint, abort, g, redirect, render_template, request, url_for
from mcp.server.auth.provider import construct_redirect_uri

from presentation.web.decorators import login_required
from presentation.web.utils import get_encryption_service, get_oauth_service

logger = logging.getLogger(__name__)

mcp_oauth_bp = Blueprint("mcp_oauth", __name__)

_SCOPE_DESCRIPTIONS = {
    "read": "View your transactions, categories, patterns, and groups",
    "readwrite": "Add and edit your transactions, categories, patterns, and groups",
}


def _client_display_name(client_row: "dict | None", fallback_client_id: str) -> str:
    """Best-effort human-readable client name from its registered metadata."""
    if not client_row:
        return fallback_client_id
    try:
        metadata = json.loads(client_row["metadata"])
    except (KeyError, TypeError, ValueError):
        return fallback_client_id
    return metadata.get("client_name") or fallback_client_id


def _describe_scopes(scopes: "list[str]") -> "list[dict[str, str]]":
    """Pair each requested scope with a human-readable description for the
    consent screen, falling back to the raw scope name for anything not in
    `_SCOPE_DESCRIPTIONS` (e.g. a future scope added to valid_scopes)."""
    return [
        {"name": scope, "description": _SCOPE_DESCRIPTIONS.get(scope, scope)}
        for scope in scopes
    ]


@mcp_oauth_bp.route("/mcp-consent", methods=["GET"])
@login_required
def consent():
    user_id = request.user_id  # type: ignore[attr-defined]
    txn = request.args.get("txn", "")

    oauth_svc = get_oauth_service()
    pending = oauth_svc.get_pending(txn)
    if pending is None:
        abort(404)

    encryption_svc = get_encryption_service()
    encrypted = encryption_svc.has_encryption(user_id)
    dek_available = bool(getattr(g, "encryption_key", None))

    if encrypted and not dek_available:
        return render_template("mcp_consent.html", txn=txn, needs_unlock=True)

    client_row = oauth_svc.get_client(pending["client_id"])
    return render_template(
        "mcp_consent.html",
        txn=txn,
        needs_unlock=False,
        client_name=_client_display_name(client_row, pending["client_id"]),
        scopes=_describe_scopes(pending.get("scopes") or []),
    )


@mcp_oauth_bp.route("/mcp-consent", methods=["POST"])
@login_required
def consent_submit():
    user_id = request.user_id  # type: ignore[attr-defined]
    txn = request.form.get("txn", "")
    action = request.form.get("action", "")

    oauth_svc = get_oauth_service()
    pending = oauth_svc.get_pending(txn)
    if pending is None:
        abort(404)

    if action != "approve":
        oauth_svc.consume_pending(txn)
        logger.info("OAuth consent denied for client %s", pending["client_id"])
        redirect_url = construct_redirect_uri(
            pending["redirect_uri"], error="access_denied", state=pending.get("state")
        )
        return redirect(redirect_url)

    encryption_svc = get_encryption_service()
    encrypted = encryption_svc.has_encryption(user_id)
    dek_b64 = getattr(g, "encryption_key", None)

    if encrypted and not dek_b64:
        # The passkey unlock didn't happen (or the unlock cookie expired)
        # between the GET and this POST - never mint a code without a DEK
        # for an encrypted account. Send the browser back to the GET
        # handler, which will show the unlock UI again.
        logger.warning("OAuth consent approved without an unlocked DEK; re-prompting")
        return redirect(url_for("mcp_oauth.consent", txn=txn))

    raw_code = oauth_svc.issue_code(user_id, pending, dek_b64)
    oauth_svc.consume_pending(txn)
    logger.info("OAuth consent approved for client %s", pending["client_id"])

    redirect_url = construct_redirect_uri(
        pending["redirect_uri"], code=raw_code, state=pending.get("state")
    )
    return redirect(redirect_url)
