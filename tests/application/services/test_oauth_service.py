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
