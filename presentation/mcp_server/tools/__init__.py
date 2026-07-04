"""Registers all MCP tool modules onto the FastMCP instance."""


def register_all(mcp) -> None:
    from presentation.mcp_server.tools import transactions, categories, patterns, groups, settings
    transactions.register(mcp)
    categories.register(mcp)
    patterns.register(mcp)
    groups.register(mcp)
    settings.register(mcp)
