import os, tempfile
import pytest
from infrastructure.persistence.sqlite.repositories.oauth_client_repository import SQLiteOAuthClientRepository
from infrastructure.persistence.sqlite.repositories.oauth_authorization_repository import SQLiteOAuthAuthorizationRepository
from infrastructure.persistence.sqlite.repositories.oauth_grant_repository import SQLiteOAuthGrantRepository

@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    yield path; os.remove(path)

def test_client_upsert_and_get(db):
    r = SQLiteOAuthClientRepository(db)
    r.upsert("cid", ["http://localhost:1/callback"], '{"client_name":"Claude"}', "2026-07-04T00:00:00+00:00")
    row = r.get("cid")
    assert row["client_id"] == "cid" and "http://localhost:1/callback" in row["redirect_uris"]
    assert r.get("missing") is None

def test_pending_and_code_roundtrip(db):
    r = SQLiteOAuthAuthorizationRepository(db)
    r.create_pending("txn", "cid", '{"state":"s"}', "t0", "t1")
    assert r.get_pending("txn")["client_id"] == "cid"
    r.delete_pending("txn"); assert r.get_pending("txn") is None
    r.create_code("h", "cid", "u@x", '["read"]', "chal", "http://localhost:1/callback", 1, None, "t1")
    assert r.get_code("h")["user_id"] == "u@x"
    r.delete_code("h"); assert r.get_code("h") is None

def test_grant_create_lookup_rotate_revoke(db):
    r = SQLiteOAuthGrantRepository(db)
    r.create("g1","u@x","cid","read","ath","ats","t9","rth","rts","t9","t0")
    assert r.get_by_at_hash("ath")["user_id"] == "u@x"
    assert r.get_by_rt_hash("rth")["grant_id"] == "g1"
    r.rotate("g1","ath2","ats2","t9","rth2","rts2","t9","rth","t_grace")
    assert r.get_by_at_hash("ath") is None
    assert r.get_by_at_hash("ath2")["grant_id"] == "g1"
    # old RT still resolvable within grace via prev_rt_hash
    assert r.get_by_rt_hash("rth")["grant_id"] == "g1"
    assert r.get_by_rt_hash("rth2")["grant_id"] == "g1"
    r.revoke_by_grant_id("g1")
    assert r.get_by_at_hash("ath2") is None
