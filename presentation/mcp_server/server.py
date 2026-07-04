"""FastMCP server instance for SpendSense."""
import os
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings

from presentation.mcp_server.auth import SpendSenseTokenVerifier


def _base_url() -> str:
    return os.getenv("MCP_BASE_URL", "http://localhost:5000")


def create_mcp_app() -> FastMCP:
    base = _base_url()
    auth = AuthSettings(
        issuer_url=base,  # type: ignore[arg-type]
        resource_server_url=base,  # type: ignore[arg-type]
    )
    # FastMCP's default Host/Origin allowlist only covers loopback addresses.
    # MCP_BASE_URL's host must be added explicitly or every real deployment
    # gets rejected with 421 Misdirected Request.
    host = urlparse(base).netloc
    transport_security = TransportSecuritySettings(
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", host],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*", base],
    )
    mcp = FastMCP(
        "SpendSense",
        token_verifier=SpendSenseTokenVerifier(),
        auth=auth,
        stateless_http=True,
        transport_security=transport_security,
    )
    from presentation.mcp_server.tools import register_all
    register_all(mcp)
    return mcp


mcp = create_mcp_app()
