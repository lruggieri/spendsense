"""Verify MCP_BASE_URL's host is allowlisted for DNS-rebinding protection.

The SDK's default Host/Origin allowlist only covers loopback addresses, so a
real deployment (MCP_BASE_URL pointing at a public host) would otherwise get
every request rejected with 421 Misdirected Request.

The allowlist is built by `build_transport_security()` and handed to
`streamable_http_app()` at the ASGI entrypoint - transport settings are not
carried on the MCPServer instance.
"""
import os
import tempfile

import pytest


@pytest.fixture
def build_transport_security():
    # Import from outside the repo dir to avoid the .env pydantic-settings crash
    # (see test_server_smoke.py for the same workaround).
    orig_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            os.chdir(tmp_dir)
            from presentation.mcp_server.server import build_transport_security as fn

            yield fn
        finally:
            os.chdir(orig_cwd)


def test_custom_host_is_allowlisted(monkeypatch, build_transport_security):
    monkeypatch.setenv("MCP_BASE_URL", "https://spendsense.dev")
    security = build_transport_security()

    assert security is not None
    assert "spendsense.dev" in security.allowed_hosts
    assert "https://spendsense.dev" in security.allowed_origins


def test_loopback_hosts_still_allowed(monkeypatch, build_transport_security):
    monkeypatch.setenv("MCP_BASE_URL", "https://spendsense.dev")
    security = build_transport_security()

    assert "localhost:*" in security.allowed_hosts
    assert "127.0.0.1:*" in security.allowed_hosts


def test_default_base_url_allows_localhost(monkeypatch, build_transport_security):
    monkeypatch.delenv("MCP_BASE_URL", raising=False)
    security = build_transport_security()

    assert "localhost:5000" in security.allowed_hosts


def test_allowlist_actually_rejects_a_foreign_host(monkeypatch, build_transport_security):
    """The settings must produce a real 421, not just hold the right strings.

    Mounted on a bare MCPServer rather than `create_mcp_app()`: with the OAuth
    provider wired in, auth returns 401 before transport security ever runs, so
    the 421 is unobservable through the authenticated app.
    """
    monkeypatch.setenv("MCP_BASE_URL", "https://spendsense.dev")

    from mcp.server.mcpserver import MCPServer
    from starlette.testclient import TestClient

    app = MCPServer("test").streamable_http_app(
        stateless_http=True,
        transport_security=build_transport_security(),
    )
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    body = {"jsonrpc": "2.0", "id": 1, "method": "ping"}

    with TestClient(app) as client:
        rejected = client.post("/mcp", headers={**headers, "Host": "evil.com"}, json=body)
        accepted = client.post("/mcp", headers={**headers, "Host": "spendsense.dev"}, json=body)

    # 421 Misdirected Request is the DNS-rebinding rejection.
    assert rejected.status_code == 421
    assert accepted.status_code == 200
