"""Verify encrypted write/read round-trip and no-DEK rejection."""
import base64
import sqlite3
from unittest.mock import patch

from infrastructure.crypto.encryption import generate_dek
from presentation.mcp_server.context import build_services
from presentation.mcp_server.tools.transactions import _classified, _serialize
from tests.presentation.mcp_server.tools.conftest import make_db

_no_embed = patch(
    "infrastructure.persistence.sqlite.factory.SQLiteDataSourceFactory.get_embedding_datasource",
    return_value=None,
)


def test_encrypted_write_then_decrypted_read():
    path = make_db()
    dek_b64 = base64.b64encode(generate_dek()).decode("ascii")

    with _no_embed:
        # With DEK: write and read back
        enc = build_services(path, "u@x.com", dek_b64)
        ok, tx_id = enc.transaction.add_new_transaction(
            "2026-06-25", "900", "Secret Cafe", "", "", "JPY"
        )
        assert ok, tx_id
        rows = [_serialize(t) for t in _classified(enc).values()]
        assert any(r["description"] == "Secret Cafe" for r in rows)

        # Without DEK: description is opaque placeholder
        plain = build_services(path, "u@x.com", None)
        rows2 = [_serialize(t) for t in _classified(plain).values()]
        assert all(r["description"] != "Secret Cafe" for r in rows2)


def test_no_dek_update_rejected():
    path = make_db()
    dek_b64 = base64.b64encode(generate_dek()).decode("ascii")

    enc = build_services(path, "u@x.com", dek_b64)
    ok, tx_id = enc.transaction.add_new_transaction(
        "2026-06-25", "900", "Hidden", "", "", "JPY"
    )
    assert ok

    plain = build_services(path, "u@x.com", None)
    ok2, msg = plain.transaction.update_transaction(tx_id, "2026-06-25", "900", "changed", "")
    assert not ok2, "update of encrypted tx without DEK should fail"
