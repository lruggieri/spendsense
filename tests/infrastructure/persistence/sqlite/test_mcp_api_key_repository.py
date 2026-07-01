import os
import tempfile

from infrastructure.persistence.sqlite.repositories.mcp_api_key_repository import (
    SQLiteMCPApiKeyRepository,
)


def _repo():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return SQLiteMCPApiKeyRepository(path), path


def test_create_and_lookup_by_hash():
    repo, path = _repo()
    try:
        repo.create("kid1", "u@x.com", "hash123", "read", "laptop",
                    "2026-06-24T00:00:00Z", None)
        row = repo.get_by_token_hash("hash123")
        assert row["user_id"] == "u@x.com"
        assert row["scope"] == "read"
        assert row["revoked"] == 0
        assert repo.get_by_token_hash("nope") is None
    finally:
        os.remove(path)


def test_revoke_and_list():
    repo, path = _repo()
    try:
        repo.create("kid1", "u@x.com", "h1", "readwrite", "a", "2026-06-24T00:00:00Z", None)
        assert len(repo.list_for_user("u@x.com")) == 1
        assert repo.revoke("u@x.com", "kid1") is True
        assert repo.get_by_token_hash("h1")["revoked"] == 1
    finally:
        os.remove(path)


def test_touch_last_used():
    repo, path = _repo()
    try:
        repo.create("kid2", "u@x.com", "h2", "read", "phone",
                    "2026-06-24T00:00:00Z", None)
        repo.touch_last_used("kid2", "2026-06-25T12:00:00Z")
        row = repo.get_by_token_hash("h2")
        assert row["last_used_at"] == "2026-06-25T12:00:00Z"
    finally:
        os.remove(path)


def test_revoke_wrong_user_returns_false():
    repo, path = _repo()
    try:
        repo.create("kid3", "owner@x.com", "h3", "read", "x",
                    "2026-06-24T00:00:00Z", None)
        assert repo.revoke("other@x.com", "kid3") is False
        assert repo.get_by_token_hash("h3")["revoked"] == 0
    finally:
        os.remove(path)
