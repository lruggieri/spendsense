from presentation.mcp_server.tools import transactions as tx_tools
from presentation.mcp_server.tools.transactions import _classified, _get_transaction, _serialize


class _FakeMCP:
    """Minimal stand-in for MCPServer's `@mcp.tool()` decorator: captures the
    decorated function by name instead of registering it with a real server,
    so registered tool bodies can be invoked directly in tests."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def test_add_and_list(svcs_and_path):
    svcs, _ = svcs_and_path
    ok, result = svcs.transaction.add_new_transaction(
        "2026-06-25", "1500", "Coffee", "", "", "JPY"
    )
    assert ok, result
    default_currency = svcs.user_settings.get_default_currency()
    rows = [_serialize(svcs, t, default_currency) for t in _classified(svcs).values()]
    assert any(r["description"] == "Coffee" for r in rows)


def test_get_transaction(svcs_and_path):
    svcs, _ = svcs_and_path
    ok, tx_id = svcs.transaction.add_new_transaction(
        "2026-06-25", "900", "Lunch", "", "", "JPY"
    )
    assert ok
    tx_dict = _classified(svcs)
    default_currency = svcs.user_settings.get_default_currency()
    row = _serialize(svcs, tx_dict[tx_id], default_currency) if tx_id in tx_dict else None
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


def test_amount_is_major_unit_decimal_not_minor_units(svcs_and_path):
    """Regression test: amount must be a decimal in major units (e.g. 5.99),
    never the raw minor-unit integer (e.g. 599)."""
    svcs, _ = svcs_and_path
    ok, tx_id = svcs.transaction.add_new_transaction(
        "2026-06-25", "5.99", "Coffee", "", "", "USD"
    )
    assert ok, tx_id
    tx_dict = _classified(svcs)
    default_currency = svcs.user_settings.get_default_currency()
    row = _serialize(svcs, tx_dict[tx_id], default_currency)
    assert row["amount"] == 5.99
    assert row["currency"] == "USD"


def test_converted_amount_same_currency_matches_amount(svcs_and_path):
    """When the transaction currency matches the user's default currency,
    converted_amount/converted_currency mirror amount/currency exactly."""
    svcs, _ = svcs_and_path
    default_currency = svcs.user_settings.get_default_currency()
    ok, tx_id = svcs.transaction.add_new_transaction(
        "2026-06-25", "12.34", "Snack", "", "", default_currency
    )
    assert ok, tx_id
    tx_dict = _classified(svcs)
    row = _serialize(svcs, tx_dict[tx_id], default_currency)
    assert row["converted_amount"] == row["amount"]
    assert row["converted_currency"] == row["currency"] == default_currency


def test_get_transaction_returns_none_for_missing_id(svcs_and_path):
    svcs, _ = svcs_and_path
    assert _get_transaction(svcs, "does-not-exist") is None


def test_list_transactions_tool_returns_converted_fields(svcs_and_path, monkeypatch):
    """Exercise the actual registered `list_transactions` tool body (not just
    the `_serialize`/`_classified` helpers), confirming it fetches the
    default currency once and returns the new fields end-to-end."""
    svcs, _ = svcs_and_path
    ok, tx_id = svcs.transaction.add_new_transaction(
        "2026-06-25", "5.99", "Coffee", "", "", "USD"
    )
    assert ok, tx_id

    fake_mcp = _FakeMCP()
    tx_tools.register(fake_mcp)
    monkeypatch.setattr(tx_tools, "get_tool_context", lambda: (svcs, "read"))

    rows = fake_mcp.tools["list_transactions"]()
    row = next(r for r in rows if r["id"] == tx_id)
    assert row["amount"] == 5.99
    assert row["currency"] == "USD"
    assert row["converted_currency"] == svcs.user_settings.get_default_currency()


def test_converted_amount_cross_currency(svcs_and_path):
    """When the user's default currency differs from the transaction's
    currency, converted_amount reflects an actual conversion."""
    svcs, _ = svcs_and_path
    ok, msg = svcs.user_settings.update_user_settings(currency="USD")
    assert ok, msg
    ok, tx_id = svcs.transaction.add_new_transaction(
        "2026-06-25", "1000", "Ramen", "", "", "JPY"
    )
    assert ok, tx_id
    tx_dict = _classified(svcs)
    default_currency = svcs.user_settings.get_default_currency()
    assert default_currency == "USD"
    row = _serialize(svcs, tx_dict[tx_id], default_currency)
    assert row["currency"] == "JPY"
    assert row["amount"] == 1000.0
    assert row["converted_currency"] == "USD"
    assert isinstance(row["converted_amount"], float)
    assert row["converted_amount"] != row["amount"]
    assert row["converted_amount"] > 0
