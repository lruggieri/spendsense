"""Cover require_write enforcement and write branches through the actual
registered @mcp.tool() functions, not just the underlying service calls."""
from unittest.mock import patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from presentation.mcp_server.tools import transactions


class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


@pytest.fixture
def tools(svcs_and_path):
    svcs, _ = svcs_and_path
    fake_mcp = _FakeMCP()
    transactions.register(fake_mcp)
    return fake_mcp.tools, svcs


def test_add_transaction_rejects_read_scope(tools):
    registered, svcs = tools
    with patch.object(transactions, "get_tool_context", return_value=(svcs, "read")):
        with pytest.raises(ToolError, match="read-only"):
            registered["add_transaction"](
                date="2026-06-25", amount="1000", description="Test"
            )


def test_add_transaction_succeeds_with_readwrite_scope(tools):
    registered, svcs = tools
    with patch.object(transactions, "get_tool_context", return_value=(svcs, "readwrite")):
        result = registered["add_transaction"](
            date="2026-06-25", amount="1000", description="Test Coffee"
        )
    assert result["description"] == "Test Coffee"


def test_update_transaction_comment_rejects_read_scope(tools):
    registered, svcs = tools
    with patch.object(transactions, "get_tool_context", return_value=(svcs, "readwrite")):
        tx = registered["add_transaction"](
            date="2026-06-25", amount="500", description="Lunch"
        )
    with patch.object(transactions, "get_tool_context", return_value=(svcs, "read")):
        with pytest.raises(ToolError, match="read-only"):
            registered["update_transaction_comment"](tx_id=tx["id"], comment="edited")
