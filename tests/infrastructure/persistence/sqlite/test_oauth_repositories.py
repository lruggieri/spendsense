import os, tempfile
import pytest
from domain.repositories.oauth_repository import OAuthEnvelopeRewrite
from infrastructure.persistence.sqlite.repositories.oauth_client_repository import SQLiteOAuthClientRepository
from infrastructure.persistence.sqlite.repositories.oauth_authorization_repository import SQLiteOAuthAuthorizationRepository
from infrastructure.persistence.sqlite.repositories.oauth_grant_repository import SQLiteOAuthGrantRepository
from infrastructure.persistence.sqlite.repositories.encryption_repository import SQLiteEncryptionRepository

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


def test_rotate_with_envelopes_unencrypted_behaves_like_rotate(db):
    """Without `envelopes`, rotate_with_envelopes is just rotate() (same CAS)."""
    r = SQLiteOAuthGrantRepository(db)
    r.create("g3", "u@x", "cid", "read", "ath", "ats", "t9", "rth", "rts", "t9", "t0")

    assert r.rotate_with_envelopes(
        "g3", "ath2", "ats2", "t9", "rth2", "rts2", "t9", "rth", "t_grace"
    ) is True
    assert r.get_by_at_hash("ath2")["grant_id"] == "g3"

    # Stale CAS guard (someone else already rotated) -> False, no changes.
    assert r.rotate_with_envelopes(
        "g3", "ath3", "ats3", "t9", "rth3", "rts3", "t9", "rth", "t_grace2"
    ) is False
    assert r.get_by_at_hash("ath3") is None
    assert r.get_by_at_hash("ath2")["grant_id"] == "g3"


def test_rotate_with_envelopes_writes_all_three_envelopes_atomically(db):
    """The grant CAS and the 3 envelope writes (prev/at/rt) land in one commit."""
    r = SQLiteOAuthGrantRepository(db)
    enc = SQLiteEncryptionRepository(db)
    r.create("g4", "u@x", "cid", "read", "ath", "ats", "t9", "rth", "rts", "t9", "t0")

    # Seed the CURRENT oauthrt envelope, as issue_code()/exchange_code() would.
    enc.store_wrapped_dek("u@x", "oauthrt:g4", b"old-rt-wrapped", "old-rt-salt", wrapper_type="oauth_rt")
    enc.store_wrapped_dek("u@x", "oauthat:g4", b"old-at-wrapped", "old-at-salt", wrapper_type="oauth_at")

    envelopes = OAuthEnvelopeRewrite(
        user_id="u@x",
        new_at_wrapped=b"new-at-wrapped",
        new_at_salt_b64="new-at-salt",
        new_rt_wrapped=b"new-rt-wrapped",
        new_rt_salt_b64="new-rt-salt",
    )
    ok = r.rotate_with_envelopes(
        "g4", "ath2", "ats2", "t9", "rth2", "rts2", "t9", "rth", "t_grace",
        envelopes=envelopes,
    )
    assert ok is True

    # Grant row rotated.
    assert r.get_by_at_hash("ath2")["grant_id"] == "g4"
    assert r.get_by_at_hash("ath") is None

    # New envelopes present under the new secrets' credential ids.
    assert enc.get_wrapped_dek("u@x", "oauthat:g4") == b"new-at-wrapped"
    assert enc.get_prf_salt("u@x", "oauthat:g4") == "new-at-salt"
    assert enc.get_wrapped_dek("u@x", "oauthrt:g4") == b"new-rt-wrapped"
    assert enc.get_prf_salt("u@x", "oauthrt:g4") == "new-rt-salt"

    # The OLD rt envelope was preserved verbatim under the ":prev" slot.
    assert enc.get_wrapped_dek("u@x", "oauthrt:g4:prev") == b"old-rt-wrapped"
    assert enc.get_prf_salt("u@x", "oauthrt:g4:prev") == "old-rt-salt"


def test_rotate_with_envelopes_lost_race_rolls_back_envelopes_too(db):
    """If the grants-table CAS loses, envelope writes must NOT persist either.

    This is the crux of the whole fix: a losing caller's freshly-minted
    envelopes must be structurally impossible to observe from another
    connection - not merely unreachable via the grant row.
    """
    r = SQLiteOAuthGrantRepository(db)
    enc = SQLiteEncryptionRepository(db)
    r.create("g5", "u@x", "cid", "read", "ath", "ats", "t9", "rth", "rts", "t9", "t0")
    enc.store_wrapped_dek("u@x", "oauthrt:g5", b"original-rt-wrapped", "orig-salt", wrapper_type="oauth_rt")

    # Someone else rotates first, moving rt_hash away from "rth".
    assert r.rotate_with_envelopes(
        "g5", "ath-winner", "ats", "t9", "rth-winner", "rts", "t9", "rth", "t_grace"
    ) is True

    # A second caller that still thinks rt_hash == "rth" tries to rotate too,
    # carrying its own (independently minted) envelope writes.
    loser_envelopes = OAuthEnvelopeRewrite(
        user_id="u@x",
        new_at_wrapped=b"loser-at-wrapped",
        new_at_salt_b64="loser-at-salt",
        new_rt_wrapped=b"loser-rt-wrapped",
        new_rt_salt_b64="loser-rt-salt",
    )
    ok = r.rotate_with_envelopes(
        "g5", "ath-loser", "ats", "t9", "rth-loser", "rts", "t9", "rth", "t_grace2",
        envelopes=loser_envelopes,
    )
    assert ok is False

    # None of the loser's envelope writes are visible anywhere - not under
    # the new credential ids, and the original (winner-untouched, since the
    # winner's call passed no envelopes) oauthrt envelope is unchanged.
    assert enc.get_wrapped_dek("u@x", "oauthat:g5") is None
    assert enc.get_wrapped_dek("u@x", "oauthrt:g5") == b"original-rt-wrapped"
    assert enc.get_wrapped_dek("u@x", "oauthrt:g5:prev") is None
    assert r.get_by_at_hash("ath-loser") is None
    assert r.get_by_rt_hash("rth-loser") is None
    assert r.get_by_at_hash("ath-winner")["grant_id"] == "g5"


def test_rotate_with_envelopes_uses_begin_immediate_for_cross_connection_exclusion(db):
    """A second connection's BEGIN IMMEDIATE genuinely blocks until this one commits.

    This is what makes the fix correct across separate OS processes (not
    just separate threads/GIL): SQLite's own RESERVED lock, acquired by
    BEGIN IMMEDIATE, forces real serialization between independent
    connections sharing the same file - not merely a best-effort compare-
    and-swap that a differently-timed writer could still slip past.
    """
    import threading
    import time

    from infrastructure.persistence.sqlite.connection import get_connection

    r = SQLiteOAuthGrantRepository(db)
    r.create("g6", "u@x", "cid", "read", "ath", "ats", "t9", "rth", "rts", "t9", "t0")

    order = []
    release_holder = threading.Event()

    def holder():
        conn = get_connection(db)
        conn.execute("BEGIN IMMEDIATE")
        order.append("holder-acquired")
        release_holder.wait(timeout=2)
        conn.rollback()
        conn.close()
        order.append("holder-released")

    t = threading.Thread(target=holder)
    t.start()
    # Give the holder thread time to actually acquire BEGIN IMMEDIATE first.
    time.sleep(0.1)

    def rotator():
        result = r.rotate_with_envelopes(
            "g6", "ath2", "ats2", "t9", "rth2", "rts2", "t9", "rth", "t_grace"
        )
        order.append("rotate-done")
        assert result is True

    rt = threading.Thread(target=rotator)
    rt.start()
    time.sleep(0.2)
    # The rotator must still be blocked behind the holder's RESERVED lock.
    assert "rotate-done" not in order
    release_holder.set()
    rt.join(timeout=3)
    t.join(timeout=3)

    assert order == ["holder-acquired", "holder-released", "rotate-done"]
