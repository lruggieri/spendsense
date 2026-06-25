"""MCP tools: category read and write."""
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp.exceptions import ToolError

from presentation.mcp.auth import get_tool_context, require_write


def register(mcp) -> None:
    @mcp.tool()
    def list_categories() -> List[Dict[str, Any]]:
        """List all categories in hierarchy order."""
        svcs, _ = get_tool_context()
        result = []
        for cat in svcs.category.get_all_categories():
            result.append({
                "id": cat.id,
                "name": cat.name,
                "description": getattr(cat, "description", ""),
                "parent_id": getattr(cat, "parent_id", ""),
            })
        return result

    @mcp.tool()
    def create_category(
        name: str, description: str = "", parent_id: str = ""
    ) -> Dict[str, Any]:
        """Create a category. parent_id empty for top-level. Requires readwrite scope."""
        svcs, scope = get_tool_context()
        require_write(scope)
        ok, msg, cat_id = svcs.category.create_category(name, description, parent_id)
        if not ok:
            raise ToolError(f"failed to create category: {msg}")
        return {"id": cat_id, "name": name}

    @mcp.tool()
    def update_category(
        category_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> bool:
        """Update a category's name, description, and/or parent. Requires readwrite scope."""
        svcs, scope = get_tool_context()
        require_write(scope)
        ok, msg = svcs.category.update_category(
            category_id, name=name, description=description, parent_id=parent_id
        )
        if not ok:
            raise ToolError(f"failed to update category: {msg}")
        return True
