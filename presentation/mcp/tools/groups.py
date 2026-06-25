"""MCP tools: group read and write."""
from typing import Any, Dict, List

from mcp.server.fastmcp.exceptions import ToolError

from presentation.mcp.auth import get_tool_context, require_write


def register(mcp) -> None:
    @mcp.tool()
    def list_groups() -> List[Dict[str, Any]]:
        """List all groups."""
        svcs, _ = get_tool_context()
        return [{"id": g.id, "name": g.name} for g in svcs.group.get_all_groups()]

    @mcp.tool()
    def create_group(name: str) -> Dict[str, Any]:
        """Create a group. Requires readwrite scope."""
        svcs, scope = get_tool_context()
        require_write(scope)
        ok, msg, gid = svcs.group.create_group(name)
        if not ok:
            raise ToolError(f"failed to create group: {msg}")
        return {"id": gid, "name": name}

    @mcp.tool()
    def update_group(group_id: str, name: str) -> bool:
        """Rename a group. Requires readwrite scope."""
        svcs, scope = get_tool_context()
        require_write(scope)
        ok, msg = svcs.group.update_group(group_id, name)
        if not ok:
            raise ToolError(f"failed to update group: {msg}")
        return True
