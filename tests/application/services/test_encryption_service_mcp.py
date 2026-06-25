import base64
import os
import tempfile

from application.services.encryption_service import EncryptionService
from infrastructure.persistence.sqlite.repositories.encryption_repository import (
    SQLiteEncryptionRepository,
)
from infrastructure.persistence.sqlite.repositories.mcp_api_key_repository import (
    SQLiteMCPApiKeyRepository,
)
from infrastructure.crypto.encryption import generate_dek


def _svc():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    enc = SQLiteEncryptionRepository(path)
    mcp = SQLiteMCPApiKeyRepository(path)
    return EncryptionService(encryption_repo=enc, mcp_api_key_datasource=mcp), path


def test_create_resolve_and_unwrap_encrypted():
    svc, path = _svc()
    try:
        dek_b64 = base64.b64encode(generate_dek()).decode("ascii")
        raw = svc.create_mcp_api_key("u@x.com", "readwrite", "laptop", None, dek_b64)
        assert raw.startswith("ssk_")
        resolved = svc.resolve_mcp_api_key(raw)
        assert resolved["user_id"] == "u@x.com"
        assert resolved["scope"] == "readwrite"
        assert resolved["encrypted"] is True
        # DEK round-trips back to the original
        assert svc.unwrap_dek_for_api_key(raw) == dek_b64
    finally:
        os.remove(path)


def test_resolve_rejects_unknown_and_revoked():
    svc, path = _svc()
    try:
        raw = svc.create_mcp_api_key("u@x.com", "read", "a", None, None)  # plaintext acct
        assert svc.resolve_mcp_api_key("ssk_bogus") is None
        assert svc.unwrap_dek_for_api_key(raw) is None  # no encryption -> None
        key_id = svc.resolve_mcp_api_key(raw)["key_id"]
        assert svc.revoke_mcp_api_key("u@x.com", key_id) is True
        assert svc.resolve_mcp_api_key(raw) is None
    finally:
        os.remove(path)
