"""Tests for OAuth DEK-bridge / envelope methods on EncryptionService."""

import base64
import os
import tempfile

import pytest

from application.services.encryption_service import EncryptionService
from infrastructure.persistence.sqlite.repositories.encryption_repository import (
    SQLiteEncryptionRepository,
)


@pytest.fixture
def svc():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield EncryptionService(encryption_repo=SQLiteEncryptionRepository(path))
    os.remove(path)


def test_code_bridge_then_token_envelopes_same_dek(svc):
    dek = base64.b64encode(os.urandom(32)).decode()
    svc.oauth_wrap_dek_for_code("u@x", "rawcode", "cid1", dek)
    got = svc.oauth_unwrap_dek_for_code("u@x", "rawcode", "cid1")
    assert got == dek  # code envelope round-trips

    at_salt, rt_salt = svc.oauth_create_token_envelopes("u@x", "g1", "AT", "RT", dek)
    assert svc.oauth_unwrap_dek_for_access_token("u@x", "g1", "AT", at_salt) == dek
    assert svc.oauth_unwrap_dek_for_refresh_token("u@x", "g1", "RT", rt_salt) == dek

    # wrong token cannot unwrap
    with pytest.raises(Exception):
        svc.oauth_unwrap_dek_for_access_token("u@x", "g1", "WRONG", at_salt)


def test_unencrypted_account_has_no_envelopes(svc):
    assert svc.oauth_unwrap_dek_for_code("u@x", "rawcode", "cidX") is None


def test_oauth_delete_code_envelope(svc):
    dek = base64.b64encode(os.urandom(32)).decode()
    svc.oauth_wrap_dek_for_code("u@x", "rawcode", "cid1", dek)
    svc.oauth_delete_code_envelope("u@x", "cid1")
    assert svc.oauth_unwrap_dek_for_code("u@x", "rawcode", "cid1") is None


def test_oauth_delete_grant_envelopes(svc):
    dek = base64.b64encode(os.urandom(32)).decode()
    at_salt, rt_salt = svc.oauth_create_token_envelopes("u@x", "g1", "AT", "RT", dek)
    svc.oauth_delete_grant_envelopes("u@x", "g1")
    assert svc.oauth_unwrap_dek_for_access_token("u@x", "g1", "AT", at_salt) is None
    assert svc.oauth_unwrap_dek_for_refresh_token("u@x", "g1", "RT", rt_salt) is None
    # deleting again (e.g. a "-prev" envelope that was never created) must be a no-op
    svc.oauth_delete_grant_envelopes("u@x", "g1")


def test_oauth_rewrap_for_rotation_without_prev(svc):
    dek = base64.b64encode(os.urandom(32)).decode()
    svc.oauth_create_token_envelopes("u@x", "g1", "AT", "RT", dek)

    new_at_salt, new_rt_salt = svc.oauth_rewrap_for_rotation(
        "u@x", "g1", "AT2", "RT2", dek, keep_prev_rt=None
    )

    assert svc.oauth_unwrap_dek_for_access_token("u@x", "g1", "AT2", new_at_salt) == dek
    assert svc.oauth_unwrap_dek_for_refresh_token("u@x", "g1", "RT2", new_rt_salt) == dek
    # old tokens no longer work
    with pytest.raises(Exception):
        svc.oauth_unwrap_dek_for_access_token("u@x", "g1", "AT", new_at_salt)


def test_oauth_rewrap_for_rotation_with_prev(svc):
    dek = base64.b64encode(os.urandom(32)).decode()
    svc.oauth_create_token_envelopes("u@x", "g1", "AT", "RT", dek)

    new_at_salt, new_rt_salt = svc.oauth_rewrap_for_rotation(
        "u@x", "g1", "AT2", "RT2", dek, keep_prev_rt="RT"
    )

    # new tokens unwrap correctly
    assert svc.oauth_unwrap_dek_for_access_token("u@x", "g1", "AT2", new_at_salt) == dek
    assert svc.oauth_unwrap_dek_for_refresh_token("u@x", "g1", "RT2", new_rt_salt) == dek

    # the previous refresh token's envelope was preserved under oauthrt:{grant_id}:prev
    # and can still be unwrapped with the OLD refresh token secret.
    prev_salt = svc._encryption_repo.get_prf_salt("u@x", "oauthrt:g1:prev")
    assert prev_salt is not None
    assert svc.oauth_unwrap_dek_for_refresh_token("u@x", "g1:prev", "RT", prev_salt) == dek
