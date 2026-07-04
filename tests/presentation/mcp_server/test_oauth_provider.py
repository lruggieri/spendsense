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

def test_full_code_exchange_bridges_dek(provider):
    import base64, os, asyncio
    from mcp.shared.auth import OAuthClientInformationFull
    svc = provider.service
    dek = base64.b64encode(os.urandom(32)).decode()
    pending = {"client_id":"cid","scopes":["read"],"code_challenge":"chal",
               "redirect_uri":"http://localhost:9/callback","redirect_uri_provided_explicitly":True,"resource":None}
    raw_code = svc.issue_code("u@x", pending, dek)
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    ac = asyncio.run(provider.load_authorization_code(ci, raw_code))
    assert ac is not None and ac.client_id == "cid"
    tok = asyncio.run(provider.exchange_authorization_code(ci, ac))
    assert tok.access_token and tok.refresh_token
    # the minted AT unwraps the SAME dek via the grant
    resolved = svc.resolve_access(tok.access_token)
    assert resolved["user_id"] == "u@x"
    assert svc.unwrap_dek(tok.access_token, resolved) == dek
    # code + its envelope are consumed
    assert asyncio.run(provider.load_authorization_code(ci, raw_code)) is None

def test_load_authorization_code_rejects_wrong_client(provider):
    svc = provider.service
    pending = {"client_id":"cid","scopes":["read"],"code_challenge":"chal",
               "redirect_uri":"http://localhost:9/callback","redirect_uri_provided_explicitly":True,"resource":None}
    raw_code = svc.issue_code("u@x", pending, None)
    other_ci = OAuthClientInformationFull(client_id="other", redirect_uris=["http://localhost:9/callback"])
    assert asyncio.run(provider.load_authorization_code(other_ci, raw_code)) is None

def test_exchange_code_without_dek_yields_no_envelope(provider):
    svc = provider.service
    pending = {"client_id":"cid","scopes":["read"],"code_challenge":"chal",
               "redirect_uri":"http://localhost:9/callback","redirect_uri_provided_explicitly":True,"resource":None}
    raw_code = svc.issue_code("u@x", pending, None)
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    ac = asyncio.run(provider.load_authorization_code(ci, raw_code))
    tok = asyncio.run(provider.exchange_authorization_code(ci, ac))
    resolved = svc.resolve_access(tok.access_token)
    assert svc.unwrap_dek(tok.access_token, resolved) is None

def test_exchange_unknown_code_raises_invalid_grant(provider):
    from mcp.server.auth.provider import AuthorizationCode, TokenError
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    fake_ac = AuthorizationCode(
        code="bogus", scopes=["read"], expires_at=9999999999.0, client_id="cid",
        code_challenge="chal", redirect_uri="http://localhost:9/callback",
        redirect_uri_provided_explicitly=True, resource=None,
    )
    with pytest.raises(TokenError):
        asyncio.run(provider.exchange_authorization_code(ci, fake_ac))
