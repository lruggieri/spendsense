"""Verify the OAuth authorization-server routes are mounted on the FastMCP app.

Confirms `create_mcp_app()` wires `SpendSenseOAuthProvider` in as
`auth_server_provider`, which makes FastMCP mount the `/authorize`, `/token`,
and `/register` (dynamic client registration) routes via
`mcp.server.auth.routes.create_auth_routes`.
"""
import os
import tempfile


def test_oauth_routes_mounted():
    # Import from outside the repo dir to avoid the .env pydantic-settings
    # crash (see test_server_smoke.py for the same workaround).
    orig = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        try:
            os.chdir(d)
            from presentation.mcp_server.server import create_mcp_app

            app = create_mcp_app()
            paths = {getattr(r, "path", None) for r in app.streamable_http_app().routes}
            assert "/authorize" in paths
            assert "/token" in paths
            assert "/register" in paths
            assert "/revoke" in paths
            assert "/.well-known/oauth-authorization-server" in paths
        finally:
            os.chdir(orig)
