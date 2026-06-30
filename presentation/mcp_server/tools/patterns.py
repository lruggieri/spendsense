"""MCP tools: regexp pattern read and write."""
from typing import Any, Dict, List

from mcp.server.fastmcp.exceptions import ToolError

from presentation.mcp_server.auth import get_tool_context, require_write


def register(mcp) -> None:
    @mcp.tool()
    def list_regexp_patterns() -> List[Dict[str, Any]]:
        """List all regexp classification patterns."""
        svcs, _ = get_tool_context()
        return svcs.pattern.get_all_patterns()

    @mcp.tool()
    def create_regexp_pattern(
        rules: List[Dict[str, Any]], category_id: str, name: str = ""
    ) -> Dict[str, Any]:
        """Create a regexp pattern. rules is a list of rule dicts. Requires readwrite scope."""
        svcs, scope = get_tool_context()
        require_write(scope)
        ok, msg, pat_id = svcs.pattern.create_pattern(rules, category_id, name)
        if not ok:
            raise ToolError(f"failed to create pattern: {msg}")
        return {"id": pat_id, "name": name}

    @mcp.tool()
    def update_regexp_pattern(
        pattern_id: str,
        rules: List[Dict[str, Any]],
        category_id: str,
        name: str = "",
    ) -> bool:
        """Update an existing regexp pattern. Requires readwrite scope."""
        svcs, scope = get_tool_context()
        require_write(scope)
        ok, msg = svcs.pattern.update_pattern(pattern_id, rules, category_id, name)
        if not ok:
            raise ToolError(f"failed to update pattern: {msg}")
        return True
