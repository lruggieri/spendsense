"""Smoke test: verify expected tools are registered on the FastMCP instance."""


def test_expected_tools_registered():
    # Import server module from outside the spendsense dir to avoid .env sandbox crash
    import os
    import sys

    # FastMCP reads pydantic-settings from .env on import — run in /tmp to skip it
    orig_cwd = os.getcwd()
    try:
        os.chdir("/tmp")
        from presentation.mcp_server.server import mcp
        import asyncio

        tools = asyncio.run(mcp.list_tools())
        if isinstance(tools, dict):
            names = set(tools.keys())
        else:
            names = {t.name for t in tools}

        assert "list_transactions" in names
        assert "create_category" in names
        assert "list_regexp_patterns" in names
        assert "list_groups" in names
    finally:
        os.chdir(orig_cwd)
