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

def test_replaying_a_consumed_code_raises_invalid_grant_not_assertion_error(provider):
    """Regression test for the TOCTOU race: a code must be single-use.

    Exchanging the same authorization code twice must never crash with an
    uncaught AssertionError from the DEK-unwrap path (which happened when a
    second read-then-delete exchange found the code row but its envelope had
    already been deleted by the first exchange). The second attempt must
    cleanly raise TokenError(invalid_grant), exactly like an unknown code.
    """
    from mcp.server.auth.provider import TokenError
    import base64, os as _os

    svc = provider.service
    dek = base64.b64encode(_os.urandom(32)).decode()
    pending = {"client_id": "cid", "scopes": ["read"], "code_challenge": "chal",
               "redirect_uri": "http://localhost:9/callback",
               "redirect_uri_provided_explicitly": True, "resource": None}
    raw_code = svc.issue_code("u@x", pending, dek)
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    ac = asyncio.run(provider.load_authorization_code(ci, raw_code))
    assert ac is not None

    # First exchange succeeds and consumes the code.
    tok = asyncio.run(provider.exchange_authorization_code(ci, ac))
    assert tok.access_token and tok.refresh_token

    # Replaying the same code must fail cleanly (invalid_grant), not crash.
    with pytest.raises(TokenError):
        asyncio.run(provider.exchange_authorization_code(ci, ac))

def test_concurrent_exchange_of_same_code_only_one_winner():
    """Two threads racing exchange_code() on the SAME code: exactly one wins.

    This exercises the atomic consume_code() DELETE...RETURNING claim
    directly against OAuthService (bypassing the async provider layer, since
    threads need a synchronous call). Before the fix, both threads could
    pass a read-then-delete check and mint two independent token pairs.
    """
    import threading
    from application.services.oauth_service import OAuthService

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        svc = OAuthService(db_path=path)
        pending = {"client_id": "cid", "scopes": ["read"], "code_challenge": "chal",
                   "redirect_uri": "http://localhost:9/callback",
                   "redirect_uri_provided_explicitly": True, "resource": None}
        raw_code = svc.issue_code("u@x", pending, None)

        results = [None, None]

        def worker(i):
            results[i] = svc.exchange_code("cid", raw_code)

        t1 = threading.Thread(target=worker, args=(0,))
        t2 = threading.Thread(target=worker, args=(1,))
        t1.start(); t2.start()
        t1.join(); t2.join()

        non_none = [r for r in results if r is not None]
        assert len(non_none) == 1
        assert results.count(None) == 1
    finally:
        os.remove(path)
