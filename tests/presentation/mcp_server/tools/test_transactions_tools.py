from presentation.mcp_server.tools import transactions as tx


def test_add_and_list(svcs_and_path):
    svcs, _ = svcs_and_path
    ok, result = svcs.transaction.add_new_transaction(
        "2026-06-25", "1500", "Coffee", "", "", "JPY"
    )
    assert ok, result
    rows = tx._list_transactions(svcs, page=0)
    assert any(r["description"] == "Coffee" for r in rows)


def test_get_transaction(svcs_and_path):
    svcs, _ = svcs_and_path
    ok, tx_id = svcs.transaction.add_new_transaction(
        "2026-06-25", "900", "Lunch", "", "", "JPY"
    )
    assert ok
    row = tx._get_transaction(svcs, tx_id)
    assert row is not None and row["id"] == tx_id


def _list_transactions(svcs, page=0):
    txs = svcs.transaction.get_all_transactions_filtered()
    start = page * 50
    return [_ser(t) for t in txs[start: start + 50]]


def _get_transaction(svcs, tx_id):
    t = svcs.transaction.get_transaction_by_id(tx_id)
    return _ser(t) if t else None


def _ser(t):
    return {
        "id": t.id,
        "description": t.description,
        "date": t.date,
        "amount": t.amount,
    }
