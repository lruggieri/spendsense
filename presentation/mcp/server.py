"""FastMCP server instance for SpendSense."""
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings

from presentation.mcp.auth import SpendSenseTokenVerifier


def _base_url() -> str:
    return os.getenv("MCP_BASE_URL", "http://localhost:5000")


def create_mcp_app() -> FastMCP:
    base = _base_url()
    auth = AuthSettings(
        issuer_url=base,  # type: ignore[arg-type]
        resource_server_url=base,  # type: ignore[arg-type]
    )
    mcp = FastMCP(
        "SpendSense",
        token_verifier=SpendSenseTokenVerifier(),
        auth=auth,
        stateless_http=True,
    )
    from presentation.mcp.tools import register_all
    register_all(mcp)
    return mcp


mcp = create_mcp_app()
