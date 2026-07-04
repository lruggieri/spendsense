"""Tests for OAuthService: client registration and authorization-transaction bootstrap."""
import json
import os
import tempfile

import pytest

from application.services.oauth_service import OAuthService


@pytest.fixture
def svc():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield OAuthService(db_path=path)
    os.remove(path)


def test_register_and_get_client(svc):
    svc.register_client("cid", ["http://localhost:9/callback"], json.dumps({"client_id": "cid"}))
    got = svc.get_client("cid")
    assert got is not None
    assert got["client_id"] == "cid"
    assert got["redirect_uris"] == ["http://localhost:9/callback"]
    assert json.loads(got["metadata"]) == {"client_id": "cid"}


def test_get_client_missing_returns_none(svc):
    assert svc.get_client("does-not-exist") is None


def test_register_client_upsert_overwrites_metadata(svc):
    svc.register_client("cid", ["http://localhost:9/callback"], json.dumps({"v": 1}))
    svc.register_client("cid", ["http://localhost:9/other"], json.dumps({"v": 2}))
    got = svc.get_client("cid")
    assert got["redirect_uris"] == ["http://localhost:9/other"]
    assert json.loads(got["metadata"]) == {"v": 2}


def test_begin_authorization_returns_txn_id_and_persists_pending(svc):
    svc.register_client("cid", ["http://localhost:9/callback"], json.dumps({"client_id": "cid"}))
    params = {"state": "st", "scopes": ["read"], "redirect_uri": "http://localhost:9/callback"}
    txn_id = svc.begin_authorization("cid", params)

    assert isinstance(txn_id, str) and len(txn_id) > 20
    pending = svc._authorization_repo.get_pending(txn_id)
    assert pending is not None
    assert pending["client_id"] == "cid"
    assert json.loads(pending["params"]) == params


def test_begin_authorization_generates_unique_txn_ids(svc):
    svc.register_client("cid", ["http://localhost:9/callback"], json.dumps({"client_id": "cid"}))
    txn1 = svc.begin_authorization("cid", {"scopes": ["read"]})
    txn2 = svc.begin_authorization("cid", {"scopes": ["read"]})
    assert txn1 != txn2


# =============================================================================
# resolve_access / unwrap_dek / revoke: unify OAuth grants + legacy API keys
# =============================================================================


def test_resolve_access_falls_back_to_legacy_api_key(svc):
    import base64
    from infrastructure.crypto.encryption import generate_dek

    dek_b64 = base64.b64encode(generate_dek()).decode("ascii")
    raw = svc._encryption.create_mcp_api_key("u@x", "readwrite", "laptop", None, dek_b64)

    resolved = svc.resolve_access(raw)
    assert resolved is not None
    assert resolved["kind"] == "apikey"
    assert resolved["user_id"] == "u@x"
    assert resolved["scope"] == "readwrite"
    assert "key_id" in resolved

    # DEK still round-trips via the legacy path.
    assert svc.unwrap_dek(raw, resolved) == dek_b64


def test_resolve_access_prefers_oauth_grant_when_both_could_exist(svc):
    pending = {"client_id": "cid", "scopes": ["read"], "code_challenge": "c",
               "redirect_uri": "http://localhost:9/callback",
               "redirect_uri_provided_explicitly": True, "resource": None}
    raw_code = svc.issue_code("u@x", pending, None)
    result = svc.exchange_code("cid", raw_code)

    resolved = svc.resolve_access(result["access_token"])
    assert resolved["kind"] == "oauth"
    assert resolved["user_id"] == "u@x"
    assert resolved["grant_id"]


def test_resolve_access_garbage_token_returns_none(svc):
    assert svc.resolve_access("totally-bogus-token") is None


def test_revoke_kills_oauth_grant_and_its_envelopes(svc):
    import base64
    from infrastructure.crypto.encryption import generate_dek

    dek_b64 = base64.b64encode(generate_dek()).decode("ascii")
    pending = {"client_id": "cid", "scopes": ["read"], "code_challenge": "c",
               "redirect_uri": "http://localhost:9/callback",
               "redirect_uri_provided_explicitly": True, "resource": None}
    raw_code = svc.issue_code("u@x", pending, dek_b64)
    result = svc.exchange_code("cid", raw_code)

    svc.revoke(result["access_token"])

    assert svc.resolve_access(result["access_token"]) is None
    # The envelope is gone too - even resolving by refresh token can't
    # recover the DEK anymore (grant is revoked outright).
    assert svc.resolve_refresh("cid", result["refresh_token"]) is None


def test_revoke_via_refresh_token_also_kills_the_grant(svc):
    pending = {"client_id": "cid", "scopes": ["read"], "code_challenge": "c",
               "redirect_uri": "http://localhost:9/callback",
               "redirect_uri_provided_explicitly": True, "resource": None}
    raw_code = svc.issue_code("u@x", pending, None)
    result = svc.exchange_code("cid", raw_code)

    svc.revoke(result["refresh_token"])

    assert svc.resolve_access(result["access_token"]) is None
    assert svc.resolve_refresh("cid", result["refresh_token"]) is None


def test_revoke_is_a_noop_for_legacy_api_key(svc):
    import base64
    from infrastructure.crypto.encryption import generate_dek

    dek_b64 = base64.b64encode(generate_dek()).decode("ascii")
    raw = svc._encryption.create_mcp_api_key("u@x", "read", "laptop", None, dek_b64)

    svc.revoke(raw)  # must not raise

    resolved = svc.resolve_access(raw)
    assert resolved is not None
    assert resolved["kind"] == "apikey"


def test_revoke_garbage_token_is_a_noop(svc):
    svc.revoke("totally-bogus-token")  # must not raise
