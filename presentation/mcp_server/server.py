"""FastMCP server instance for SpendSense."""
import os
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.transport_security import TransportSecuritySettings

from config import get_database_path
from presentation.mcp_server.oauth_provider import SpendSenseOAuthProvider


def _base_url() -> str:
    return os.getenv("MCP_BASE_URL", "http://localhost:5000")


def create_mcp_app() -> FastMCP:
    base = _base_url()
    auth = AuthSettings(
        issuer_url=base,  # type: ignore[arg-type]
        resource_server_url=base,  # type: ignore[arg-type]
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["read", "readwrite"],
            default_scopes=["read"],
        ),
        revocation_options=RevocationOptions(enabled=True),
    )
    # FastMCP's default Host/Origin allowlist only covers loopback addresses.
    # MCP_BASE_URL's host must be added explicitly or every real deployment
    # gets rejected with 421 Misdirected Request.
    host = urlparse(base).netloc
    transport_security = TransportSecuritySettings(
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", host],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*", base],
    )
    # FastMCP rejects passing both `auth_server_provider` and `token_verifier`
    # (they're mutually exclusive - see FastMCP.__init__ in the installed
    # SDK). Passing only `auth_server_provider` is sufficient: FastMCP
    # auto-derives its token verification from the provider's
    # `load_access_token()`, which already resolves both OAuth access tokens
    # and legacy API keys via `OAuthService.resolve_access()`, so the
    # standalone `SpendSenseTokenVerifier` is no longer needed here.
    provider = SpendSenseOAuthProvider(db_path=get_database_path())
    mcp = FastMCP(
        "SpendSense",
        auth_server_provider=provider,
        auth=auth,
        stateless_http=True,
        transport_security=transport_security,
    )
    from presentation.mcp_server.tools import register_all
    register_all(mcp)
    return mcp


mcp = create_mcp_app()
