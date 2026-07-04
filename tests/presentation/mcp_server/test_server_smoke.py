"""Smoke test: verify expected tools are registered on the FastMCP instance."""


def test_expected_tools_registered():
    # Import server module from outside the spendsense dir to avoid .env sandbox crash
    import asyncio
    import os
    import tempfile

    # FastMCP reads pydantic-settings from .env on import — run in a scratch dir to skip it
    orig_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            os.chdir(tmp_dir)
            from presentation.mcp_server.server import mcp

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
