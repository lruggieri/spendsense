import base64
import os
import tempfile
from unittest.mock import patch

import pytest

from infrastructure.crypto.encryption import generate_dek


def _make_key(scope, encrypted, monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    import presentation.mcp_server.auth as auth
    monkeypatch.setattr(auth, "_db_path", lambda: path)
    svc = auth._encryption_service()
    dek_b64 = base64.b64encode(generate_dek()).decode("ascii") if encrypted else None
    raw = svc.create_mcp_api_key("u@x.com", scope, "test-key", None, dek_b64)
    return auth, raw, path


def test_require_write_rejects_read():
    import presentation.mcp_server.auth as auth
    with pytest.raises(Exception):
        auth.require_write("read")
    auth.require_write("readwrite")  # should not raise


def test_require_write_accepts_multi_scope_grant():
    """A grant with scope "read readwrite" (space-joined, e.g. a client that
    requested both scopes at once) must be treated as having write access -
    require_write must check membership, not do an exact-string match."""
    import presentation.mcp_server.auth as auth
    auth.require_write("read readwrite")  # should not raise
    auth.require_write("readwrite read")  # order must not matter


def test_get_tool_context_no_token_raises(monkeypatch):
    import presentation.mcp_server.auth as auth
    from mcp.server.fastmcp.exceptions import ToolError
    monkeypatch.setattr(auth, "get_access_token", lambda: None)
    with pytest.raises(ToolError, match="unauthorized"):
        auth.get_tool_context()


def test_get_tool_context_rate_limited_raises(monkeypatch):
    from mcp.server.auth.provider import AccessToken
    from mcp.server.fastmcp.exceptions import ToolError
    auth, raw, path = _make_key("read", False, monkeypatch)
    try:
        monkeypatch.setattr(
            auth,
            "get_access_token",
            lambda: AccessToken(token=raw, client_id="u@x.com", scopes=["read"], expires_at=None),
        )
        monkeypatch.setattr(auth._rate_limiter, "check", lambda *_a, **_k: False)
        with pytest.raises(ToolError, match="rate limit"):
            auth.get_tool_context()
    finally:
        os.remove(path)


def test_get_tool_context_rate_limited_before_resolving_invalid_token(monkeypatch):
    """Rate limiting must be checked before the token is resolved against the DB,
    so a garbage/invalid token still gets throttled instead of skipping straight
    to an "invalid token" error via a full DB round-trip."""
    from mcp.server.auth.provider import AccessToken
    from mcp.server.fastmcp.exceptions import ToolError
    import presentation.mcp_server.auth as auth

    monkeypatch.setattr(
        auth,
        "get_access_token",
        lambda: AccessToken(
            token="ssk_totally_garbage", client_id="whatever", scopes=[], expires_at=None
        ),
    )
    monkeypatch.setattr(auth._rate_limiter, "check", lambda *_a, **_k: False)
    with pytest.raises(ToolError, match="rate limit"):
        auth.get_tool_context()


def test_get_tool_context_revoked_key_raises_tool_error(monkeypatch):
    from mcp.server.auth.provider import AccessToken
    from mcp.server.fastmcp.exceptions import ToolError
    auth, raw, path = _make_key("read", False, monkeypatch)
    try:
        monkeypatch.setattr(
            auth,
            "get_access_token",
            lambda: AccessToken(token=raw, client_id="u@x.com", scopes=["read"], expires_at=None),
        )
        svc = auth._encryption_service()
        resolved = svc.resolve_mcp_api_key(raw)
        svc.revoke_mcp_api_key("u@x.com", resolved["key_id"])
        with pytest.raises(ToolError, match="unauthorized"):
            auth.get_tool_context()
    finally:
        os.remove(path)


def test_get_tool_context_valid_token_returns_services(monkeypatch):
    from mcp.server.auth.provider import AccessToken
    from tests.presentation.mcp_server.tools.conftest import make_db
    import presentation.mcp_server.auth as auth
    path = make_db()
    monkeypatch.setattr(auth, "_db_path", lambda: path)
    svc = auth._encryption_service()
    raw = svc.create_mcp_api_key("u@x.com", "readwrite", "test-key", None, None)
    try:
        monkeypatch.setattr(
            auth,
            "get_access_token",
            lambda: AccessToken(
                token=raw, client_id="u@x.com", scopes=["readwrite"], expires_at=None
            ),
        )
        with patch(
            "infrastructure.persistence.sqlite.factory.SQLiteDataSourceFactory."
            "get_embedding_datasource",
            return_value=None,
        ):
            services, scope = auth.get_tool_context()
        assert scope == "readwrite"
        assert services.transaction is not None
    finally:
        os.remove(path)
