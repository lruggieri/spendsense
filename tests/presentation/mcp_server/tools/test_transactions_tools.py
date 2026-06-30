from presentation.mcp_server.tools.transactions import _classified, _serialize


def test_add_and_list(svcs_and_path):
    svcs, _ = svcs_and_path
    ok, result = svcs.transaction.add_new_transaction(
        "2026-06-25", "1500", "Coffee", "", "", "JPY"
    )
    assert ok, result
    rows = [_serialize(t) for t in _classified(svcs).values()]
    assert any(r["description"] == "Coffee" for r in rows)


def test_get_transaction(svcs_and_path):
    svcs, _ = svcs_and_path
    ok, tx_id = svcs.transaction.add_new_transaction(
        "2026-06-25", "900", "Lunch", "", "", "JPY"
    )
    assert ok
    tx_dict = _classified(svcs)
    row = _serialize(tx_dict[tx_id]) if tx_id in tx_dict else None
    assert row is not None and row["id"] == tx_id
