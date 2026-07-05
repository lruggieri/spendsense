"""get_tool_context() must resolve the SpendSense user_id via
OAuthService.resolve_access/unwrap_dek for BOTH token kinds - never via
AccessToken.client_id (which, for an OAuth token, is the registered OAuth
client id, e.g. "cid" - deliberately different from the user_id below so a
regression back to `token_obj.client_id` fails loudly)."""
import base64
import os
from unittest.mock import patch

import pytest
from mcp.server.auth.provider import AccessToken
from mcp.server.fastmcp.exceptions import ToolError

from infrastructure.crypto.encryption import generate_dek
from tests.presentation.mcp_server.tools.conftest import make_db


@pytest.fixture
def db_path(monkeypatch):
    path = make_db()
    import presentation.mcp_server.auth as auth
    monkeypatch.setattr(auth, "_db_path", lambda: path)
    yield path
    os.remove(path)


def _embedding_patch():
    return patch(
        "infrastructure.persistence.sqlite.factory.SQLiteDataSourceFactory."
        "get_embedding_datasource",
        return_value=None,
    )


def test_get_tool_context_resolves_oauth_token_user_id_and_scope_and_dek(db_path):
    import presentation.mcp_server.auth as auth

    svc = auth._oauth_service()
    dek_b64 = base64.b64encode(generate_dek()).decode("ascii")
    pending = {
        "client_id": "cid",
        "scopes": ["readwrite"],
        "code_challenge": "chal",
        "redirect_uri": "http://localhost:9/callback",
        "redirect_uri_provided_explicitly": True,
        "resource": None,
    }
    raw_code = svc.issue_code("real-user@example.com", pending, dek_b64)
    result = svc.exchange_code("cid", raw_code)
    assert result is not None
    access_token = result["access_token"]

    # client_id on the AccessToken is the OAuth client ("cid"), NOT the user.
    monkeypatch_token = AccessToken(
        token=access_token, client_id="cid", scopes=["readwrite"], expires_at=None
    )
    with patch.object(auth, "get_access_token", lambda: monkeypatch_token):
        with _embedding_patch():
            services, scope = auth.get_tool_context()

    assert scope == "readwrite"
    assert services.transaction is not None
    # The resolved user_id must be the real SpendSense user, never "cid".
    assert services.transaction.user_id == "real-user@example.com"


def test_get_tool_context_maps_invalid_unwrap_to_unauthorized_tool_error(db_path, monkeypatch):
    """A concurrent refresh() can rewrap the DEK envelope under new AT/RT
    secrets between this request resolving the grant row and unwrapping its
    envelope, so `unwrap_dek` -> `oauth_unwrap_dek_for_access_token` ->
    `unwrap_key` can raise `cryptography.hazmat.primitives.keywrap.InvalidUnwrap`
    for an otherwise-resolvable token. get_tool_context() must map that to the
    same clean "unauthorized: invalid token" ToolError it raises for any other
    unresolvable/invalid token, not let it propagate as an uncaught 500."""
    import presentation.mcp_server.auth as auth

    svc = auth._oauth_service()
    dek_b64 = base64.b64encode(generate_dek()).decode("ascii")
    pending = {
        "client_id": "cid",
        "scopes": ["readwrite"],
        "code_challenge": "chal",
        "redirect_uri": "http://localhost:9/callback",
        "redirect_uri_provided_explicitly": True,
        "resource": None,
    }
    raw_code = svc.issue_code("real-user@example.com", pending, dek_b64)
    result = svc.exchange_code("cid", raw_code)
    assert result is not None
    access_token = result["access_token"]

    def _raise_invalid_unwrap(*_args, **_kwargs):
        from cryptography.hazmat.primitives.keywrap import InvalidUnwrap
        raise InvalidUnwrap()

    monkeypatch.setattr(auth.OAuthService, "unwrap_dek", _raise_invalid_unwrap)

    token_obj = AccessToken(
        token=access_token, client_id="cid", scopes=["readwrite"], expires_at=None
    )
    with patch.object(auth, "get_access_token", lambda: token_obj):
        with _embedding_patch():
            with pytest.raises(ToolError, match="unauthorized: invalid token"):
                auth.get_tool_context()


def test_get_tool_context_still_resolves_legacy_api_key(db_path):
    import presentation.mcp_server.auth as auth

    enc_svc = auth._encryption_service()
    raw = enc_svc.create_mcp_api_key("legacy-user@example.com", "read", "test-key", None, None)

    with patch.object(
        auth,
        "get_access_token",
        lambda: AccessToken(
            token=raw, client_id="legacy-user@example.com", scopes=["read"], expires_at=None
        ),
    ):
        with _embedding_patch():
            services, scope = auth.get_tool_context()

    assert scope == "read"
    assert services.transaction.user_id == "legacy-user@example.com"


def test_get_tool_context_rejects_garbage_token(db_path):
    import presentation.mcp_server.auth as auth

    with patch.object(
        auth,
        "get_access_token",
        lambda: AccessToken(token="ssk_bad", client_id="whatever", scopes=[], expires_at=None),
    ):
        with pytest.raises(ToolError, match="unauthorized"):
            auth.get_tool_context()
