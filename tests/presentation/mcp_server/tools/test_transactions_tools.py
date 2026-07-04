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


def test_list_transactions_filtered_by_group(svcs_and_path):
    svcs, _ = svcs_and_path
    ok, in_group_id = svcs.transaction.add_new_transaction(
        "2026-06-25", "1000", "In group", "", "", "JPY"
    )
    assert ok
    ok, other_id = svcs.transaction.add_new_transaction(
        "2026-06-25", "2000", "Not in group", "", "", "JPY"
    )
    assert ok
    svcs.transaction.add_group_to_transaction(in_group_id, "grp1")

    tx_dict = _classified(svcs)
    txs = svcs.transaction.get_all_transactions_filtered(
        group_id="grp1", transactions=list(tx_dict.values())
    )
    ids = [t.id for t in txs]
    assert ids == [in_group_id]
    assert other_id not in ids
