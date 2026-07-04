import asyncio, tempfile, os, pytest
from mcp.shared.auth import OAuthClientInformationFull
from mcp.server.auth.provider import AuthorizationParams
from presentation.mcp_server.oauth_provider import SpendSenseOAuthProvider

@pytest.fixture
def provider(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    monkeypatch.setenv("MCP_BASE_URL", "https://spendsense.dev")
    yield SpendSenseOAuthProvider(db_path=path); os.remove(path)

def test_register_and_get_client(provider):
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    asyncio.run(provider.register_client(ci))
    got = asyncio.run(provider.get_client("cid"))
    assert got is not None and str(got.redirect_uris[0]) == "http://localhost:9/callback"

def test_authorize_returns_consent_redirect(provider):
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    asyncio.run(provider.register_client(ci))
    params = AuthorizationParams(state="st", scopes=["read"], code_challenge="chal",
        redirect_uri="http://localhost:9/callback", redirect_uri_provided_explicitly=True, resource=None)
    url = asyncio.run(provider.authorize(ci, params))
    assert url.startswith("https://spendsense.dev/mcp-consent?txn=")
