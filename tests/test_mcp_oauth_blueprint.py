"""Tests for the /mcp-consent Flask page (OAuth consent + passkey-unlock gate)."""
import json
from unittest.mock import MagicMock, patch


PENDING = {
    "client_id": "cid",
    "scopes": ["read"],
    "code_challenge": "challenge",
    "redirect_uri": "https://client.example/callback",
    "redirect_uri_provided_explicitly": True,
    "resource": None,
    "state": "xyz",
}

CLIENT_ROW = {
    "client_id": "cid",
    "redirect_uris": ["https://client.example/callback"],
    "metadata": json.dumps({"client_id": "cid", "client_name": "Claude Code"}),
}


def _mock_services(pending=PENDING, has_encryption=False):
    oauth_svc = MagicMock()
    oauth_svc.get_pending.return_value = pending
    oauth_svc.get_client.return_value = CLIENT_ROW
    encryption_svc = MagicMock()
    encryption_svc.has_encryption.return_value = has_encryption
    return oauth_svc, encryption_svc


def _patched(oauth_svc, encryption_svc):
    return patch.multiple(
        "presentation.web.blueprints.mcp_oauth",
        get_oauth_service=MagicMock(return_value=oauth_svc),
        get_encryption_service=MagicMock(return_value=encryption_svc),
    )


def test_get_consent_unencrypted_account_shows_scope(authenticated_client):
    oauth_svc, encryption_svc = _mock_services(has_encryption=False)
    with _patched(oauth_svc, encryption_svc):
        resp = authenticated_client.get("/mcp-consent?txn=abc123")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "read" in body
    assert "Claude Code" in body
    # Should not show the passkey-unlock UI when nothing needs unlocking.
    assert "authenticateWithPRF" not in body or "unlock-btn" not in body


def test_get_consent_encrypted_account_without_dek_shows_unlock_ui(authenticated_client):
    oauth_svc, encryption_svc = _mock_services(has_encryption=True)
    with _patched(oauth_svc, encryption_svc):
        resp = authenticated_client.get("/mcp-consent?txn=abc123")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "unlock-btn" in body
    # Consent buttons must not be reachable until unlocked.
    assert "Approve" not in body


def test_get_consent_encrypted_account_with_dek_shows_consent(app, authenticated_client):
    from flask import g as flask_g

    @app.before_request
    def _set_encryption_key():
        flask_g.encryption_key = "fake-dek-b64"

    oauth_svc, encryption_svc = _mock_services(has_encryption=True)
    with _patched(oauth_svc, encryption_svc):
        resp = authenticated_client.get("/mcp-consent?txn=abc123")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Approve" in body


def test_get_consent_unknown_txn_404s(authenticated_client):
    oauth_svc, encryption_svc = _mock_services(pending=None)
    with _patched(oauth_svc, encryption_svc):
        resp = authenticated_client.get("/mcp-consent?txn=does-not-exist")

    assert resp.status_code == 404


def test_post_approve_redirects_with_code_and_state(authenticated_client):
    oauth_svc, encryption_svc = _mock_services(has_encryption=False)
    oauth_svc.issue_code.return_value = "raw-code-value"
    with _patched(oauth_svc, encryption_svc):
        resp = authenticated_client.post(
            "/mcp-consent", data={"txn": "abc123", "action": "approve"}
        )

    assert resp.status_code in (302, 303)
    location = resp.headers["Location"]
    assert location.startswith("https://client.example/callback")
    assert "code=raw-code-value" in location
    assert "state=xyz" in location
    oauth_svc.issue_code.assert_called_once()
    oauth_svc.consume_pending.assert_called_once_with("abc123")


def test_post_deny_redirects_with_access_denied(authenticated_client):
    oauth_svc, encryption_svc = _mock_services(has_encryption=False)
    with _patched(oauth_svc, encryption_svc):
        resp = authenticated_client.post(
            "/mcp-consent", data={"txn": "abc123", "action": "deny"}
        )

    assert resp.status_code in (302, 303)
    location = resp.headers["Location"]
    assert location.startswith("https://client.example/callback")
    assert "error=access_denied" in location
    assert "state=xyz" in location
    oauth_svc.issue_code.assert_not_called()
    oauth_svc.consume_pending.assert_called_once_with("abc123")


def test_post_approve_encrypted_account_without_dek_does_not_issue_code(authenticated_client):
    """Never mint a code without a DEK for an encrypted account - redirect back to unlock."""
    oauth_svc, encryption_svc = _mock_services(has_encryption=True)
    with _patched(oauth_svc, encryption_svc):
        resp = authenticated_client.post(
            "/mcp-consent", data={"txn": "abc123", "action": "approve"}
        )

    oauth_svc.issue_code.assert_not_called()
    assert resp.status_code in (302, 303)
    assert "/mcp-consent" in resp.headers["Location"]


def test_post_unknown_txn_404s(authenticated_client):
    oauth_svc, encryption_svc = _mock_services(pending=None)
    with _patched(oauth_svc, encryption_svc):
        resp = authenticated_client.post(
            "/mcp-consent", data={"txn": "does-not-exist", "action": "approve"}
        )

    assert resp.status_code == 404
