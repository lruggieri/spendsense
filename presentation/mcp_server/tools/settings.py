"""MCP tool: read-only user settings."""
from typing import Any, Dict

from presentation.mcp_server.auth import get_tool_context


def register(mcp) -> None:
    @mcp.tool()
    def get_user_settings() -> Dict[str, Any]:
        """Get the user's currency and language settings (read-only)."""
        svcs, _ = get_tool_context()
        s = svcs.user_settings.get_user_settings()
        return {"currency": s.currency, "language": s.language}
