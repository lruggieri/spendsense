"""Verify MCP_BASE_URL's host is allowlisted for DNS-rebinding protection.

FastMCP's default Host/Origin allowlist only covers loopback addresses, so a
real deployment (MCP_BASE_URL pointing at a public host) would otherwise get
every request rejected with 421 Misdirected Request.
"""
import os
import tempfile

import pytest


@pytest.fixture
def create_mcp_app():
    # Import from outside the repo dir to avoid the .env pydantic-settings crash
    # (see test_server_smoke.py for the same workaround).
    orig_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            os.chdir(tmp_dir)
            from presentation.mcp_server.server import create_mcp_app as fn

            yield fn
        finally:
            os.chdir(orig_cwd)


def test_custom_host_is_allowlisted(monkeypatch, create_mcp_app):
    monkeypatch.setenv("MCP_BASE_URL", "https://spendsense.dev")
    mcp = create_mcp_app()

    security = mcp.settings.transport_security
    assert security is not None
    assert "spendsense.dev" in security.allowed_hosts
    assert "https://spendsense.dev" in security.allowed_origins


def test_loopback_hosts_still_allowed(monkeypatch, create_mcp_app):
    monkeypatch.setenv("MCP_BASE_URL", "https://spendsense.dev")
    mcp = create_mcp_app()

    security = mcp.settings.transport_security
    assert "localhost:*" in security.allowed_hosts
    assert "127.0.0.1:*" in security.allowed_hosts


def test_default_base_url_allows_localhost(monkeypatch, create_mcp_app):
    monkeypatch.delenv("MCP_BASE_URL", raising=False)
    mcp = create_mcp_app()

    security = mcp.settings.transport_security
    assert "localhost:5000" in security.allowed_hosts
