"""Tests for the MCP API key management web endpoints."""
from unittest.mock import MagicMock, patch


def test_list_keys_empty(authenticated_client):
    mock_svc = MagicMock()
    mock_svc.list_mcp_api_keys.return_value = []
    with patch("presentation.web.blueprints.api_keys.get_encryption_service", return_value=mock_svc):
        resp = authenticated_client.get("/api/mcp-keys")
    assert resp.status_code == 200
    assert resp.get_json()["keys"] == []


def test_create_key_success(authenticated_client):
    mock_svc = MagicMock()
    mock_svc.create_mcp_api_key.return_value = "ssk_testkey123"
    with patch("presentation.web.blueprints.api_keys.get_encryption_service", return_value=mock_svc):
        resp = authenticated_client.post(
            "/api/mcp-keys/create",
            json={"scope": "read", "label": "my-laptop"},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["key"] == "ssk_testkey123"


def test_create_key_invalid_scope(authenticated_client):
    resp = authenticated_client.post(
        "/api/mcp-keys/create",
        json={"scope": "admin", "label": "test"},
    )
    assert resp.status_code == 400


def test_revoke_key_success(authenticated_client):
    mock_svc = MagicMock()
    mock_svc.revoke_mcp_api_key.return_value = True
    with patch("presentation.web.blueprints.api_keys.get_encryption_service", return_value=mock_svc):
        resp = authenticated_client.post(
            "/api/mcp-keys/revoke",
            json={"key_id": "abc-123"},
        )
    assert resp.status_code == 200
    assert resp.get_json()["revoked"] is True


def test_revoke_key_not_found(authenticated_client):
    mock_svc = MagicMock()
    mock_svc.revoke_mcp_api_key.return_value = False
    with patch("presentation.web.blueprints.api_keys.get_encryption_service", return_value=mock_svc):
        resp = authenticated_client.post(
            "/api/mcp-keys/revoke",
            json={"key_id": "no-such-key"},
        )
    assert resp.status_code == 404
