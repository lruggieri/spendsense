"""MCP server instance for SpendSense."""
import os
from urllib.parse import urlparse

from mcp.server.mcpserver import MCPServer
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.transport_security import TransportSecuritySettings

from config import get_database_path
from presentation.mcp_server.oauth_provider import (
    DEFAULT_SCOPES,
    VALID_SCOPES,
    SpendSenseOAuthProvider,
)


def _base_url() -> str:
    return os.getenv("MCP_BASE_URL", "http://localhost:5000")


def build_transport_security() -> TransportSecuritySettings:
    """Host/Origin allowlist for the streamable-HTTP transport.

    The SDK's default allowlist only covers loopback addresses. MCP_BASE_URL's
    host must be added explicitly or every real deployment gets rejected with
    421 Misdirected Request.

    Transport settings live on `streamable_http_app()` rather than the
    `MCPServer` constructor, so this is applied at the ASGI entrypoint - see
    `presentation/asgi.py`.
    """
    base = _base_url()
    host = urlparse(base).netloc
    return TransportSecuritySettings(
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", host],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*", base],
    )


def create_mcp_app() -> MCPServer:
    base = _base_url()
    auth = AuthSettings(
        issuer_url=base,  # type: ignore[arg-type]
        resource_server_url=base,  # type: ignore[arg-type]
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=VALID_SCOPES,
            default_scopes=DEFAULT_SCOPES,
        ),
        revocation_options=RevocationOptions(enabled=True),
    )
    # MCPServer rejects passing both `auth_server_provider` and `token_verifier`
    # (they're mutually exclusive - see MCPServer.__init__ in the installed
    # SDK). Passing only `auth_server_provider` is sufficient: the server
    # auto-derives its token verification from the provider's
    # `load_access_token()`, which already resolves both OAuth access tokens
    # and legacy API keys via `OAuthService.resolve_access()` - a standalone
    # token verifier duplicating that resolution would bypass the rate
    # limiter and unified resolve_access/unwrap_dek path, so none exists here.
    provider = SpendSenseOAuthProvider(db_path=get_database_path())
    mcp = MCPServer(
        "SpendSense",
        auth_server_provider=provider,
        auth=auth,
    )
    from presentation.mcp_server.tools import register_all
    register_all(mcp)
    return mcp


mcp = create_mcp_app()
