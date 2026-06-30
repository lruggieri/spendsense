import asyncio
import base64
import os
import tempfile

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


def test_verify_token_valid_and_invalid(monkeypatch):
    auth, raw, path = _make_key("read", True, monkeypatch)
    try:
        v = auth.SpendSenseTokenVerifier()
        tok = asyncio.run(v.verify_token(raw))
        assert tok is not None
        assert tok.client_id == "u@x.com"
        assert "read" in tok.scopes
        assert asyncio.run(v.verify_token("ssk_bad")) is None
    finally:
        os.remove(path)


def test_require_write_rejects_read():
    import presentation.mcp_server.auth as auth
    with pytest.raises(Exception):
        auth.require_write("read")
    auth.require_write("readwrite")  # should not raise
