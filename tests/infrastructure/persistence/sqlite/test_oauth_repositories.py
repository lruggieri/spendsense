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

def test_consume_code_is_atomic_single_use(db):
    r = SQLiteOAuthAuthorizationRepository(db)
    r.create_code("h2", "cid", "u@x", '["read"]', "chal", "http://localhost:1/callback", 1, None, "t1")
    # First claim returns the full row and removes it.
    claimed = r.consume_code("h2")
    assert claimed is not None
    assert claimed["code_hash"] == "h2"
    assert claimed["client_id"] == "cid"
    assert claimed["user_id"] == "u@x"
    assert r.get_code("h2") is None
    # Second claim on the same hash finds nothing (already consumed).
    assert r.consume_code("h2") is None

def test_consume_code_unknown_hash_returns_none(db):
    r = SQLiteOAuthAuthorizationRepository(db)
    assert r.consume_code("does-not-exist") is None

def test_grant_create_lookup_rotate_revoke(db):
    r = SQLiteOAuthGrantRepository(db)
    r.create("g1","u@x","cid","read","ath","ats","t9","rth","rts","t9","t0")
    assert r.get_by_at_hash("ath")["user_id"] == "u@x"
    assert r.get_by_rt_hash("rth")["grant_id"] == "g1"
    assert r.rotate("g1","ath2","ats2","t9","rth2","rts2","t9","rth","t_grace") is True
    assert r.get_by_at_hash("ath") is None
    assert r.get_by_at_hash("ath2")["grant_id"] == "g1"
    # old RT still resolvable within grace via prev_rt_hash
    assert r.get_by_rt_hash("rth")["grant_id"] == "g1"
    assert r.get_by_rt_hash("rth2")["grant_id"] == "g1"
    r.revoke_by_grant_id("g1")
    assert r.get_by_at_hash("ath2") is None

def test_rotate_is_a_compare_and_swap_on_rt_hash(db):
    """rotate()'s WHERE clause guards on the rt_hash the caller observed.

    This is the serialization primitive two concurrent refreshes rely on: if
    a caller's view of the grant's current rt_hash (passed as prev_rt_hash)
    is already stale by the time its UPDATE runs, the statement must match
    zero rows and leave the row untouched - never silently overwrite
    whatever the other, faster caller already wrote.
    """
    r = SQLiteOAuthGrantRepository(db)
    r.create("g2", "u@x", "cid", "read", "ath", "ats", "t9", "rth", "rts", "t9", "t0")

    # First rotation observes the true current rt_hash ("rth") -> succeeds.
    assert r.rotate("g2", "ath2", "ats2", "t9", "rth2", "rts2", "t9", "rth", "t_grace") is True

    # A second caller that *also* thought the current rt_hash was still
    # "rth" (e.g. it read the row before the first rotation committed) now
    # tries to rotate using that stale value. It must fail (False), and the
    # row must be exactly what the winner wrote - not a hybrid/corrupted mix.
    assert r.rotate("g2", "ath3", "ats3", "t9", "rth3", "rts3", "t9", "rth", "t_grace2") is False
    row = r.get_by_at_hash("ath2")
    assert row is not None and row["grant_id"] == "g2"
    assert r.get_by_at_hash("ath3") is None
    assert r.get_by_rt_hash("rth3") is None
