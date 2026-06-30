"""MCP tools: transaction read and write."""
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp.exceptions import ToolError

from presentation.mcp_server.auth import get_tool_context, require_write

_PAGE = 50


def _serialize(tx) -> Dict[str, Any]:
    src = tx.category_source
    return {
        "id": tx.id,
        "date": tx.date,
        "amount": tx.amount,
        "description": tx.description,
        "source": tx.source,
        "comment": tx.comment,
        "currency": getattr(tx, "currency", "JPY"),
        "category_id": tx.category,
        "category_source": src.value if src is not None else None,
        "groups": list(getattr(tx, "groups", []) or []),
    }


def _classified(svcs) -> Dict[str, Any]:
    """Load all transactions and apply the full classification pipeline."""
    tx_dict = {tx.id: tx for tx in svcs.transaction.get_all_transactions()}
    svcs.classification.classify_transactions(tx_dict)
    return tx_dict


def _get_transaction(svcs, tx_id: str) -> Optional[Dict[str, Any]]:
    tx_dict = _classified(svcs)
    t = tx_dict.get(tx_id)
    return _serialize(t) if t else None


def register(mcp) -> None:
    @mcp.tool()
    def list_transactions(
        category_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        page: int = 0,
    ) -> List[Dict[str, Any]]:
        """List transactions, optionally filtered. Results are paginated (50/page)."""
        svcs, _ = get_tool_context()
        tx_dict = _classified(svcs)
        txs = svcs.transaction.get_all_transactions_filtered(
            category_id=category_id,
            from_date=from_date,
            to_date=to_date,
            transactions=list(tx_dict.values()),
        )
        start = page * _PAGE
        return [_serialize(t) for t in txs[start: start + _PAGE]]

    @mcp.tool()
    def get_transaction(tx_id: str) -> Dict[str, Any]:
        """Get a single transaction by ID."""
        svcs, _ = get_tool_context()
        result = _get_transaction(svcs, tx_id)
        if result is None:
            raise ToolError(f"transaction {tx_id!r} not found")
        return result

    @mcp.tool()
    def add_transaction(
        date: str,
        amount: str,
        description: str,
        category: str = "",
        comment: str = "",
        currency: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a new transaction. Requires readwrite scope."""
        svcs, scope = get_tool_context()
        require_write(scope)
        ok, result = svcs.transaction.add_new_transaction(
            date, amount, description, category, comment, currency
        )
        if not ok:
            raise ToolError(f"failed to add transaction: {result}")
        tx = _get_transaction(svcs, result)
        if tx is None:
            raise ToolError("transaction created but not found")
        return tx

    @mcp.tool()
    def update_transaction(
        tx_id: str,
        date: str,
        amount: str,
        description: str,
        comment: str,
        currency: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing transaction's core fields. Requires readwrite scope."""
        svcs, scope = get_tool_context()
        require_write(scope)
        ok, msg = svcs.transaction.update_transaction(tx_id, date, amount, description, comment, currency)
        if not ok:
            raise ToolError(f"update failed: {msg}")
        tx = _get_transaction(svcs, tx_id)
        if tx is None:
            raise ToolError(f"transaction {tx_id!r} not found after update")
        return tx

    @mcp.tool()
    def update_transaction_comment(tx_id: str, comment: str) -> bool:
        """Update only the comment on a transaction. Requires readwrite scope."""
        svcs, scope = get_tool_context()
        require_write(scope)
        ok, _ = svcs.transaction.update_comment(tx_id, comment)
        return ok

    @mcp.tool()
    def assign_transaction_category(tx_id: str, category_id: str) -> bool:
        """Manually assign a category to a transaction. Requires readwrite scope."""
        svcs, scope = get_tool_context()
        require_write(scope)
        svcs.transaction.assign_category(tx_id, category_id)
        return True
