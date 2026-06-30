"""Verify encrypted write/read round-trip and no-DEK rejection."""
import base64
import sqlite3

from infrastructure.crypto.encryption import generate_dek
from presentation.mcp_server.context import build_services
from presentation.mcp_server.tools.transactions import _list_transactions, _get_transaction
from tests.presentation.mcp_server.tools.conftest import make_db


def test_encrypted_write_then_decrypted_read():
    path = make_db()
    dek_b64 = base64.b64encode(generate_dek()).decode("ascii")

    # With DEK: write and read back
    enc = build_services(path, "u@x.com", dek_b64)
    ok, tx_id = enc.transaction.add_new_transaction(
        "2026-06-25", "900", "Secret Cafe", "", "", "JPY"
    )
    assert ok, tx_id
    rows = _list_transactions(enc)
    assert any(r["description"] == "Secret Cafe" for r in rows)

    # Without DEK: description is opaque placeholder
    plain = build_services(path, "u@x.com", None)
    rows2 = _list_transactions(plain)
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
